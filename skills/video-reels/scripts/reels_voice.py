"""Voice-over: ElevenLabs TTS with timestamps, and Whisper checks with word timings."""

from __future__ import annotations

import base64
import difflib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from reels_common import Blocked, InputError, MissingCredential, MissingDependency, SkillError, Upstream

ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
FAST_WPS = 3.0  # words per second above which a line usually feels rushed on screen


def alignment_to_words(alignment: dict) -> list[dict]:
    """Group ElevenLabs character timings into word timings."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        raise SkillError("alignment arrays have different lengths")
    words: list[dict] = []
    cur, s, e = "", None, None
    for ch, a, b in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
            cur, s, e = "", None, None
            continue
        if s is None:
            s = a
        cur += ch
        e = b
    if cur:
        words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
    return words


def pacing(words: list[dict]) -> dict:
    if not words:
        return {"words": 0, "seconds": 0.0, "wps": 0.0}
    span = max(0.01, float(words[-1]["e"]) - float(words[0]["s"]))
    wps = len(words) / span
    return {"words": len(words), "seconds": round(span, 2), "wps": round(wps, 2), "rushed": bool(wps > FAST_WPS)}


def tts(jobs: dict, outdir: str, voice_id: str, model: str, speed: float, stability: float, similarity: float, style: float, only: list[str] | None = None, timeout: int = 120) -> dict:
    """POST each line to /with-timestamps; write <id>.mp3, <id>.alignment.json, <id>.words.json."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise MissingCredential("ELEVENLABS_API_KEY is not set (export it in your shell; never write it into files)")
    if not voice_id:
        raise InputError("--voice-id is required (or set ELEVENLABS_VOICE_ID)")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    ids = only or list(jobs)
    results = []
    for i in ids:
        if i not in jobs:
            raise InputError(f"unknown line id {i!r}")
        job = jobs[i]
        text = job if isinstance(job, str) else job.get("text", "")
        if not text.strip():
            raise InputError(f"line {i!r} has no text")
        body = {
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": stability, "similarity_boost": similarity, "style": style, "use_speaker_boost": True, "speed": speed},
        }
        req = urllib.request.Request(
            ELEVENLABS_TTS.format(voice=voice_id) + "?output_format=mp3_44100_128",
            data=json.dumps(body).encode(),
            headers={"xi-api-key": key, "content-type": "application/json", "accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode(errors="replace")
            if exc.code in (401, 403):
                raise MissingCredential(f"ElevenLabs rejected the key (HTTP {exc.code}): {detail}") from exc
            if exc.code == 429:
                raise Blocked(f"ElevenLabs rate limited (HTTP 429): {detail}") from exc
            if exc.code >= 500:
                raise Upstream(f"network error: ElevenLabs HTTP {exc.code}") from exc
            raise InputError(f"ElevenLabs HTTP {exc.code} for line {i!r}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise Upstream(f"network error: ElevenLabs unreachable: {exc}") from exc
        mp3 = out / f"{i}.mp3"
        mp3.write_bytes(base64.b64decode(payload["audio_base64"]))
        alignment = payload.get("alignment") or {}
        (out / f"{i}.alignment.json").write_text(json.dumps(alignment), encoding="utf-8")
        words = alignment_to_words(alignment) if alignment else []
        (out / f"{i}.words.json").write_text(json.dumps(words, indent=1), encoding="utf-8")
        results.append({"id": i, "audio": str(mp3), "chars": len(text), "pacing": pacing(words)})
    warnings = [f"line {r['id']} runs at {r['pacing']['wps']} words/s; consider a slower speed or fewer words" for r in results if r["pacing"].get("rushed")]
    return {"voice_id": voice_id, "model": model, "lines": results, "warnings": warnings}


# ── Whisper ──────────────────────────────────────────────────────────────

def _norm(s: str) -> list[str]:
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return [w.strip("'") for w in s.split() if w.strip("'")]


def compare(expected: str, heard: str) -> dict:
    """Word-level diff of the script line against what Whisper heard."""
    a, b = _norm(expected), _norm(heard)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    issues = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            issues.append({"op": op, "expected": " ".join(a[i1:i2]), "heard": " ".join(b[j1:j2])})
    return {"match": round(sm.ratio(), 3), "ok": not issues, "issues": issues}


def whisper(files: list[str], model: str, device: str, compute_type: str, language: str, offline: bool, expect: dict | None = None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise MissingDependency("faster-whisper is not installed: pip install faster-whisper") from exc
    for f in files:
        if not Path(f).is_file():
            raise InputError(f"audio file not found: {f}")
    try:
        m = WhisperModel(model, device=device, compute_type=compute_type, local_files_only=offline)
    except Exception as exc:  # model download / CUDA errors arrive as many types
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        if offline:
            raise MissingDependency(f"Whisper model {model!r} is not cached locally ({first})") from exc
        raise SkillError(f"could not load Whisper model {model!r}: {first}") from exc
    out = []
    warnings = []
    for f in files:
        segs, info = m.transcribe(f, language=language, word_timestamps=True, vad_filter=False, beam_size=5)
        words, text = [], []
        for s in segs:
            text.append(s.text.strip())
            words += [{"w": w.word.strip(), "s": round(float(w.start), 2), "e": round(float(w.end), 2), "p": round(float(w.probability), 2)} for w in (s.words or [])]
        item = {"file": f, "duration": round(float(info.duration), 2), "text": " ".join(text).strip(), "words": words, "pacing": pacing(words)}
        key = Path(f).stem
        if expect and key in expect:
            item["check"] = compare(expect[key], item["text"])
            if not item["check"]["ok"]:
                warnings.append(f"{key}: heard differently: " + "; ".join(f"{x['expected'] or '∅'} → {x['heard'] or '∅'}" for x in item["check"]["issues"]))
        low = [w["w"] for w in words if w["p"] < 0.5]
        if low:
            item["low_confidence"] = low
        out.append(item)
    return {"model": model, "files": out, "warnings": warnings}
