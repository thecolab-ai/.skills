#!/usr/bin/env python3
"""Bounded smoke test for video-reels.

Fixture checks always run. Audio checks need numpy + ffmpeg; the render checks
need Playwright and a Chromium; the Whisper check needs faster-whisper and a
locally cached model; the ElevenLabs check needs ELEVENLABS_API_KEY and
VIDEO_REELS_SMOKE_TTS=1. Anything unavailable is reported as [SKIP].
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
failures = 0


def ok(kind: str, msg: str) -> None:
    print(f"[PASS] {kind} {msg}", flush=True)


def skip(msg: str) -> None:
    print(f"[SKIP] {msg}", flush=True)


def fail(kind: str, msg: str) -> None:
    global failures
    failures += 1
    print(f"[FAIL] {kind} {msg}", flush=True)


def check(cond: bool, kind: str, msg: str, detail: str = "") -> bool:
    if cond:
        ok(kind, msg)
    else:
        fail(kind, f"{msg} {detail}".strip())
    return cond


def cli(*args: str, timeout: int = 120) -> tuple[int, dict | None, str]:
    done = subprocess.run([sys.executable, str(CLI), *args, "--json"], capture_output=True, text=True, timeout=timeout, check=False)
    try:
        payload = json.loads(done.stdout)
    except json.JSONDecodeError:
        payload = None
    return done.returncode, payload, (done.stderr or "")[-400:]


def has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


# ── Fixtures (always) ────────────────────────────────────────────────────

from reels_common import parse_times  # noqa: E402
from reels_voice import alignment_to_words, compare, pacing  # noqa: E402

fx = json.loads((FIX / "elevenlabs_alignment.json").read_text(encoding="utf-8"))
words = alignment_to_words(fx["alignment"])
check([w["w"] for w in words] == fx["expected_words"], "fixture", "ElevenLabs alignment groups characters into words")
check(words[0]["s"] == 0.1 and words[-1]["e"] > words[-1]["s"], "fixture", "word timings keep first-char start and last-char end")
pace = pacing(words)
check(pace["words"] == 4 and pace["wps"] == round(4 / (words[-1]["e"] - words[0]["s"]), 2) and pace["rushed"], "fixture", "pacing flags a rushed line in words per second")

cases = json.loads((FIX / "whisper_check.json").read_text(encoding="utf-8"))["cases"]
for case in cases:
    res = compare(case["expected"], case["heard"])
    good = res["ok"] == case["ok"] and (case["ok"] or {k: res["issues"][0][k] for k in ("op", "expected", "heard")} == case["issue"])
    check(good, "fixture", f"Whisper script check: {case['expected']!r} vs {case['heard']!r}", json.dumps(res))

check(parse_times(["1:2:0.5", "3,4.5"]) == [1.0, 1.5, 2.0, 3.0, 4.5], "fixture", "time ranges parse")
template = ROOT / "assets" / "template"
html = (template / "index.html").read_text(encoding="utf-8")
check(all(s in html for s in ("window.renderAt", "window.__ready", "aspect", "capture", "REEL_INFO")), "fixture", "template page exposes the capture contract")

code, payload, err = cli("--thecolab-invalid", timeout=20)
check(code == 2, "contract", "unknown option exits 2", err)

# ── Audio (numpy + ffmpeg) ───────────────────────────────────────────────

work = Path(tempfile.mkdtemp(prefix="video-reels-smoke-"))
try:
    if not (has("numpy") and shutil.which("ffmpeg") and shutil.which("ffprobe")):
        skip("audio checks need numpy and ffmpeg")
        audio_ready = False
    else:
        import numpy as np

        from reels_audio import SR, write_wav

        audio_ready = True
        # Synthetic 12 s bed: 120 bpm, first downbeat at 0.25 s, accented downbeats, a pad underneath.
        dur, bpm, phase = 12.0, 120.0, 0.25
        t = np.arange(int(dur * SR)) / SR
        music = 0.08 * (np.sin(2 * np.pi * 220 * t) + 0.6 * np.sin(2 * np.pi * 277.2 * t) + 0.5 * np.sin(2 * np.pi * 329.6 * t))
        for k, b in enumerate(np.arange(phase, dur, 60 / bpm)):
            n = int(0.25 * SR)
            i = int(b * SR)
            tt = np.arange(min(n, len(t) - i)) / SR
            f = 50 + 90 * np.exp(-tt * 40)
            gain = 0.9 if k % 4 == 0 else 0.45
            music[i:i + len(tt)] += gain * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 18)
        write_wav(work / "music.wav", np.stack([music, music], 1))
        # "VO": a voiced buzz with syllable-like amplitude, 1.0-3.0 s and 5.0-6.0 s.
        vt = np.arange(int(2.0 * SR)) / SR
        buzz = sum(np.sin(2 * np.pi * 140 * h * vt) / h for h in range(1, 12)) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * vt) ** 2) * 0.2
        write_wav(work / "vo1.wav", buzz)
        write_wav(work / "vo2.wav", buzz[: SR])

        code, p, err = cli("beats", str(work / "music.wav"))
        if check(code == 0 and p and p["ok"], "fixture", "beats runs on a synthetic bed", err):
            d = p["data"]
            check(abs(d["bpm"] - bpm) < 0.5, "fixture", f"beats finds 120 bpm (got {d['bpm']})")
            check(abs(d["first_downbeat"] - phase) < 0.03, "fixture", f"beats finds the first downbeat at 0.25 s (got {d['first_downbeat']})")
            check(abs(d["bar_seconds"] - 2.0) < 0.01, "fixture", "bar length is 2 s at 120 bpm")

        code, p, err = cli("music-edit", str(work / "music.wav"), str(work / "bed.wav"), "--bpm", "120", "--phase", "0.25", "--segments", "0:1:2,4:0:2", "--duration", "8")
        if check(code == 0 and p and p["ok"], "fixture", "music-edit assembles bar segments", err):
            from reels_common import probe

            check(abs(probe(work / "bed.wav")["duration"] - 8.0) < 0.02, "fixture", "music-edit output is exactly 8 s")

        spec = {
            "duration": 8.0,
            "music": {"path": "bed.wav", "fade_out": 1.0},
            "vo": [{"path": "vo1.wav", "at": 1.0}, {"path": "vo2.wav", "at": 5.0}],
            "sfx": [{"type": "impact", "at": 4.0, "strength": 0.6}],
            "duck_db": -11,
            "lufs": -14,
            "true_peak": -1.0,
        }
        (work / "mix.json").write_text(json.dumps(spec), encoding="utf-8")
        code, p, err = cli("mix", str(work / "mix.json"), str(work / "mix.wav"))
        if check(code == 0 and p and p["ok"], "fixture", "mix renders stems and a master", err):
            m = p["data"]["measured"]
            check(abs(m["integrated_lufs"] + 14) <= 1.0, "fixture", f"mix lands at -14 LUFS ±1 (got {m['integrated_lufs']})")
            check(m["true_peak_dbtp"] <= -1.0, "fixture", f"mix true peak is at most -1 dBTP (got {m['true_peak_dbtp']})")
            from reels_audio import decode

            mus = decode(p["data"]["stems"]["music"])
            bed = decode(work / "bed.wav")
            rms = lambda x, a, b: float(np.sqrt(np.mean(x[int(a * SR):int(b * SR)] ** 2)) + 1e-12)  # noqa: E731
            gain = lambda a, b: 20 * np.log10(rms(mus, a, b) / rms(bed, a, b))  # noqa: E731
            dip = gain(1.6, 2.4) - gain(3.8, 4.4)
            check(dip < -6, "fixture", f"music ducks under VO (dip {dip:.1f} dB)")

    # ── Render (Playwright + Chromium) ───────────────────────────────────
    proj = work / "proj"
    code, p, err = cli("init", str(proj), "--aspect", "9x16")
    check(code == 0 and (proj / "index.html").is_file() and (proj / "progress.md").is_file(), "fixture", "init copies the template and checklist", err)
    rendered = False
    if not has("playwright"):
        skip("render checks need playwright (pip install playwright)")
    elif not shutil.which("ffmpeg"):
        skip("render checks need ffmpeg")
    else:
        code, p, err = cli("render", str(proj), str(work / "r.mkv"), "--to", "90", "--scale", "0.333", "--workers", "2", "--chunk-frames", "45", timeout=180)
        if code == 3 and p and p["error"]["type"] == "dependency_missing":
            skip(f"render checks: {p['error']['message']}")
        elif check(code == 0 and p and p["ok"], "fixture", "render produces a 3 s 360p clip in 2 chunks", (p or {}).get("error", {}).get("message", err) if p else err):
            from reels_common import probe

            info = probe(work / "r.mkv")
            check((info["width"], info["height"]) == (360, 640) and abs(info["duration"] - 3.0) < 0.05, "fixture", f"rendered clip is 360x640, 3.0 s (got {info})")
            rendered = True
            code, p, err = cli("shots", str(proj), str(work / "shots"), "0.5", "2.2", "5", "--scale", "0.333", "--sheet", str(work / "sheet.png"), timeout=120)
            check(code == 0 and (work / "sheet.png").is_file() and len(p["data"]["stills"]) == 3, "fixture", "shots writes stills and a contact sheet", err)
            code, p, err = cli("determinism", str(proj), "--t", "2.1", "--pages", "2", "--scale", "0.333", timeout=120)
            check(code == 0 and p["data"]["deterministic"], "fixture", "the template renders deterministically across pages", err)
            code, p, err = cli("flicker", str(work / "r.mkv"))
            check(code == 0 and p["data"]["flagged"] == [], "fixture", "no single-frame flicker spikes in the template", json.dumps((p or {}).get("data", {}).get("flagged")))
            if audio_ready:
                code, p, err = cli("deliver", str(work / "r.mkv"), "--audio", str(work / "mix.wav"), "--outdir", str(work / "deliver"), "--name", "smoke", "--max-mb", "2", "--stills", "1", "2.5", timeout=180)
                if check(code == 0 and p and p["ok"], "fixture", "deliver writes master, social copy and stills", err):
                    d = p["data"]
                    check(d["social"]["mb"] <= 2 and len(d["stills"]) == 2 and Path(d["master"]["path"]).is_file(), "fixture", "social copy is under the size cap")
                    tp = d["social"]["loudness"]["true_peak_dbtp"]
                    check(tp is not None and tp <= -1.0, "fixture", f"encoded AAC true peak is at most -1 dBTP (got {tp})")

    # ── Whisper (optional, offline only) ─────────────────────────────────
    model = os.environ.get("VIDEO_REELS_WHISPER_MODEL", "tiny.en")
    if not has("faster_whisper"):
        skip("whisper check needs faster-whisper")
    elif not audio_ready:
        skip("whisper check needs the audio fixtures")
    else:
        code, p, err = cli("whisper", str(work / "vo1.wav"), "--model", model, "--offline", "--device", "cpu", "--compute-type", "int8", timeout=300)
        if code == 3:
            skip(f"whisper model {model} is not cached locally (set VIDEO_REELS_WHISPER_MODEL)")
        else:
            check(code == 0 and p and isinstance(p["data"]["files"][0]["words"], list), "fixture", f"whisper ({model}) returns a transcript with word timings", err)

    # ── ElevenLabs (optional live) ───────────────────────────────────────
    if os.environ.get("VIDEO_REELS_SMOKE_TTS") == "1" and os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID"):
        (work / "jobs.json").write_text(json.dumps({"l01": "Cut on the beat."}), encoding="utf-8")
        code, p, err = cli("voice", str(work / "jobs.json"), str(work / "vo"), timeout=120)
        if code == 5:
            print(f"network error: {(p or {}).get('error', {}).get('message', err)}")
        else:
            check(code == 0 and p and len(p["data"]["lines"]) == 1 and p["data"]["lines"][0]["pacing"]["words"] >= 3, "live", "ElevenLabs /with-timestamps returns audio and word timings", err)
    else:
        skip("ElevenLabs live check needs VIDEO_REELS_SMOKE_TTS=1, ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID")
finally:
    shutil.rmtree(work, ignore_errors=True)

if failures:
    print(f"{failures} check(s) failed")
    raise SystemExit(1)
