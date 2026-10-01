#!/usr/bin/env python3
"""video-reels: build, check and deliver kinetic-type video reels from an HTML canvas project.

Every subcommand takes --json. Heavy dependencies (numpy, playwright,
faster-whisper) are imported only by the commands that need them.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
from typing import Any, Callable

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL.parents[1] / "lib"))
from reels_common import InputError, SkillError, parse_times  # noqa: E402
from result_contract import result_envelope  # noqa: E402

SOURCE_NAME = "TheColab video-reels skill"
SOURCE_URL = "https://github.com/thecolab-ai/.skills/tree/main/skills/video-reels"
ASPECTS = ("9x16", "16x9", "1x1", "4x5")
TEMPLATE = SKILL / "assets" / "template"


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"error": "invalid_input", "message": message}), file=sys.stderr)
        raise SystemExit(2)


def _load_json(path: str) -> Any:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{path} is not valid JSON: {exc.msg} (line {exc.lineno})") from exc


# ── Commands ─────────────────────────────────────────────────────────────

CHECKLIST = """# progress

Handoff file: tick items as you go so another session can pick up.

- [ ] brief: audience, goal, length, format ({aspect})
- [ ] findings.md: facts with sources; illustrative items labelled
- [ ] script.md: one idea per line, long holds, VO lines with ids
- [ ] voice: lines generated, Whisper-checked, word timings saved
- [ ] music: candidates scored, bpm + bar phase found, bar-aligned edit
- [ ] reel.js: scenes keyed to bars and VO word times
- [ ] review: contact sheets + stills checked (2-3 fix passes)
- [ ] determinism + flicker checks clean
- [ ] chunked render, mix at -14 LUFS / -1 dBTP, deliver
"""

PROVENANCE = """# provenance

One row per external asset (footage, photo, music, font, logo, voice).

| asset | file | source URL | owner | licence | permission / notes |
|---|---|---|---|---|---|
"""


def cmd_init(a) -> dict:
    dest = pathlib.Path(a.dest)
    if dest.exists() and any(dest.iterdir()) and not a.force:
        raise InputError(f"{dest} exists and is not empty (use --force to overwrite template files)")
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for src in sorted(TEMPLATE.iterdir()):
        if src.is_file():
            shutil.copyfile(src, dest / src.name)
            written.append(src.name)
    html = dest / "index.html"
    html.write_text(html.read_text(encoding="utf-8").replace("get('aspect') || '9x16'", f"get('aspect') || '{a.aspect}'"), encoding="utf-8")
    for name, body in (("progress.md", CHECKLIST.format(aspect=a.aspect)), ("PROVENANCE.md", PROVENANCE)):
        if not (dest / name).exists():
            (dest / name).write_text(body, encoding="utf-8")
            written.append(name)
    for sub in ("fonts", "audio", "vo", "shots", "out"):
        (dest / sub).mkdir(exist_ok=True)
    return {"project": str(dest), "aspect": a.aspect, "files": written, "preview": f"python3 -m http.server -d {dest} 8000  # then open http://localhost:8000/?aspect={a.aspect}"}


def cmd_shots(a) -> dict:
    from reels_browser import shots

    return shots(a.project, a.outdir, parse_times(a.times), a.aspect, a.scale, a.page, a.sheet, a.cols, a.query)


def cmd_render(a) -> dict:
    from reels_browser import render

    return render(a.project, a.out, a.from_frame, a.to_frame, a.fps, a.workers, a.aspect, a.scale, a.samples, a.fast, a.grain, a.chunk_frames, a.page, a.crf, a.resume, a.query)


def cmd_determinism(a) -> dict:
    from reels_browser import determinism

    return determinism(a.project, parse_times(a.t), a.pages, parse_times(a.history), a.aspect, a.scale, a.page, a.dump, a.query)


def cmd_flicker(a) -> dict:
    from reels_video import flicker

    return flicker(a.video, a.threshold, a.luma_jump, a.start_frame)


def cmd_vdiff(a) -> dict:
    from reels_video import vdiff

    return vdiff(a.a, a.b, a.pixels, a.delta, a.start_frame)


def cmd_beats(a) -> dict:
    from reels_audio import beat_grid

    return beat_grid(a.audio, a.bpm_min, a.bpm_max, a.beats_per_bar, a.bpm, a.start, a.end)


def cmd_music_edit(a) -> dict:
    from reels_audio import music_edit, parse_segments

    return music_edit(a.source, a.out, a.bpm, a.phase, parse_segments(a.segments), a.duration, a.beats_per_bar, a.xfade, a.fade_out)


def cmd_mix(a) -> dict:
    from reels_audio import mix

    spec = _load_json(a.spec)
    if not isinstance(spec, dict):
        raise InputError("mix spec must be a JSON object")
    return mix(spec, a.out, pathlib.Path(a.spec).resolve().parent)


def cmd_voice(a) -> dict:
    from reels_voice import tts

    jobs = _load_json(a.jobs)
    if not isinstance(jobs, dict) or not jobs:
        raise InputError('jobs file must be a JSON object like {"l01": "Line text"}')
    voice = a.voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")
    return tts(jobs, a.outdir, voice, a.model, a.speed, a.stability, a.similarity, a.style, a.only or None)


def cmd_whisper(a) -> dict:
    from reels_voice import whisper

    expect = None
    if a.expect:
        expect = _load_json(a.expect)
        if not isinstance(expect, dict):
            raise InputError('--expect must be a JSON object like {"l01": "Line text"}')
        expect = {k: (v if isinstance(v, str) else v.get("text", "")) for k, v in expect.items()}
    return whisper(a.audio, a.model, a.device, a.compute_type, a.language, a.offline, expect)


def cmd_deliver(a) -> dict:
    from reels_video import deliver

    stills = parse_times(a.stills) if a.stills else []
    return deliver(a.video, a.audio, a.outdir, a.name, a.max_mb, stills, a.crf)


# ── Human output ─────────────────────────────────────────────────────────

def human(command: str, data: dict) -> None:
    if command == "init":
        print(f"Project ready at {data['project']} ({data['aspect']}). Preview: {data['preview']}")
    elif command == "shots":
        print("\n".join(data["stills"]))
        if data.get("sheet"):
            print(f"contact sheet: {data['sheet']}")
    elif command == "render":
        print(f"{data['out']}: frames {data['frames'][0]}-{data['frames'][1]} at {data['fps']} fps, {data['size'][0]}x{data['size'][1]}, {data['render_fps']} fps render")
    elif command == "determinism":
        for r in data["times"]:
            print(f"t={r['t']}: {r['distinct']} distinct")
        print("OK deterministic" if data["deterministic"] else f"NONDETERMINISTIC at {data['nondeterministic_times']}")
    elif command == "flicker":
        print(f"{data['file']}: {data['frames']} frames, {len(data['flagged'])} single-frame spikes, {len(data['luma_bumps'])} luma bumps, {len(data['hard_cuts'])} hard cuts")
        for f in data["flagged"]:
            print(f"  frame {f['frame']} t={f['t']}s spike={f['spike']} luma_jump={f['luma_jump']}")
    elif command == "vdiff":
        print(f"{data['frames']} frames, {data['differing_frames']} differ")
    elif command == "beats":
        print(f"bpm {data['bpm']}  bar {data['bar_seconds']}s  first downbeat {data['first_downbeat']}s  trim {data['trim_to_align']}s to align")
        print("bars: " + " ".join(f"{b:.2f}" for b in data["bars"][:16]) + (" …" if len(data["bars"]) > 16 else ""))
    elif command == "music-edit":
        print(f"{data['out']}: {data['duration']}s from {len(data['segments'])} segments (bar {data['bar_seconds']}s)")
    elif command == "mix":
        m = data["measured"]
        print(f"{data['out']}: {m['integrated_lufs']} LUFS, true peak {m['true_peak_dbtp']} dBTP (WAV target {data['wav_true_peak_target']})")
    elif command == "voice":
        for line in data["lines"]:
            print(f"{line['id']}: {line['audio']}  {line['pacing'].get('wps')} words/s")
    elif command == "whisper":
        for f in data["files"]:
            flag = "" if f.get("check", {}).get("ok", True) else "  ← CHECK"
            print(f"{f['file']}  {f['duration']}s  {f['text']}{flag}")
    elif command == "deliver":
        print(f"master {data['master']['path']} ({data['master']['mb']} MB)")
        print(f"social {data['social']['path']} ({data['social']['mb']} MB, limit {data['social']['limit_mb']})")
        for s in data["stills"]:
            print(f"still  {s}")
    for w in data.get("warnings", []) if isinstance(data, dict) else []:
        print(f"warning: {w}")


# ── Parser ───────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = Parser(prog="cli.py", description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true", help="emit the machine-readable result envelope")
    sub = p.add_subparsers(dest="command", metavar="{init,shots,render,determinism,flicker,vdiff,beats,music-edit,mix,voice,whisper,deliver}")

    def add(name: str, fn: Callable[[Any], dict], help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text, description=help_text)
        sp.add_argument("--json", action="store_true", help="emit the machine-readable result envelope")
        sp.set_defaults(fn=fn)
        return sp

    def page_opts(sp, scale: float = 1.0):
        sp.add_argument("--aspect", choices=ASPECTS, default="9x16", help="9x16 phone (1080x1920), 16x9 screen (1920x1080)")
        sp.add_argument("--scale", type=float, default=scale, help="canvas pixels per logical pixel (0.333 = 360 wide for 9x16)")
        sp.add_argument("--page", default="index.html", help="page inside the project")
        sp.add_argument("--query", default="", help="extra URL query flags passed to the page, e.g. 'debug=1'")

    sp = add("init", cmd_init, "copy the starter template (canvas engine, scenes, checklist) into a new project folder")
    sp.add_argument("dest")
    sp.add_argument("--aspect", choices=ASPECTS, default="9x16")
    sp.add_argument("--force", action="store_true")

    sp = add("shots", cmd_shots, "render stills at chosen times and tile them into a contact sheet")
    sp.add_argument("project")
    sp.add_argument("outdir")
    sp.add_argument("times", nargs="+", help="seconds, comma lists or start:end:step ranges")
    sp.add_argument("--sheet", help="write a contact sheet PNG here")
    sp.add_argument("--cols", type=int, default=6)
    page_opts(sp)

    sp = add("render", cmd_render, "parallel headless-Chromium render to a near-lossless x264 intermediate, in chunks")
    sp.add_argument("project")
    sp.add_argument("out", help="output .mkv")
    sp.add_argument("--from", dest="from_frame", type=int, help="first frame (default 0)")
    sp.add_argument("--to", dest="to_frame", type=int, help="end frame, exclusive (default: whole reel)")
    sp.add_argument("--fps", type=int, default=30)
    sp.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    sp.add_argument("--samples", type=int, default=1, help="motion-blur samples per frame")
    sp.add_argument("--fast", type=int, default=3, help="samples inside the reel's FAST spans")
    sp.add_argument("--grain", type=float)
    sp.add_argument("--chunk-frames", type=int, default=1800, help="frames per chunk file; 0 = one file")
    sp.add_argument("--resume", action="store_true", help="skip chunk files that already exist")
    sp.add_argument("--crf", type=int, default=4)
    page_opts(sp)

    sp = add("determinism", cmd_determinism, "render the same times on several pages after different history; every hash must match")
    sp.add_argument("project")
    sp.add_argument("--t", nargs="+", default=["1.0"], help="times to test")
    sp.add_argument("--pages", type=int, default=4)
    sp.add_argument("--history", nargs="+", default=["0", "0.5", "2.5"], help="times rendered just before each test frame")
    sp.add_argument("--dump", help="write one PNG per distinct hash here")
    page_opts(sp, 0.5)

    sp = add("flicker", cmd_flicker, "flag single-frame spikes (pop-ins, 1-frame flashes) in a rendered video")
    sp.add_argument("video")
    sp.add_argument("--threshold", type=float, default=2.0)
    sp.add_argument("--luma-jump", type=float, default=3.0)
    sp.add_argument("--start-frame", type=int, default=0)

    sp = add("vdiff", cmd_vdiff, "compare two renders of the same range frame by frame")
    sp.add_argument("a")
    sp.add_argument("b")
    sp.add_argument("--pixels", type=int, default=50, help="flag frames with more differing pixels than this")
    sp.add_argument("--delta", type=int, default=8, help="per-pixel luma difference that counts")
    sp.add_argument("--start-frame", type=int, default=0)

    sp = add("beats", cmd_beats, "find bpm, beat phase, first downbeat and the bar grid of a music file")
    sp.add_argument("audio")
    sp.add_argument("--bpm", type=float, help="known bpm: only solve phase and downbeat")
    sp.add_argument("--bpm-min", type=float, default=70)
    sp.add_argument("--bpm-max", type=float, default=180)
    sp.add_argument("--beats-per-bar", type=int, default=4)
    sp.add_argument("--start", type=float, default=0.0)
    sp.add_argument("--end", type=float)

    sp = add("music-edit", cmd_music_edit, "assemble a bar-aligned music bed from source bars with short crossfades")
    sp.add_argument("source")
    sp.add_argument("out")
    sp.add_argument("--bpm", type=float, required=True)
    sp.add_argument("--phase", type=float, required=True, help="first downbeat in the source (seconds)")
    sp.add_argument("--segments", required=True, help="video_start:source_bar:bars, comma separated, e.g. 0:4:6,12:16:7")
    sp.add_argument("--duration", type=float, required=True)
    sp.add_argument("--beats-per-bar", type=int, default=4)
    sp.add_argument("--xfade", type=float, default=0.025)
    sp.add_argument("--fade-out", type=float, default=1.75)

    sp = add("mix", cmd_mix, "mix music, VO and SFX from a JSON spec; duck music under VO; master to -14 LUFS / -1 dBTP")
    sp.add_argument("spec", help="mix spec JSON (see references/audio.md)")
    sp.add_argument("out", help="output WAV")

    sp = add("voice", cmd_voice, "ElevenLabs TTS with character timestamps (needs ELEVENLABS_API_KEY)")
    sp.add_argument("jobs", help='JSON object {"l01": "Line text", ...}')
    sp.add_argument("outdir")
    sp.add_argument("--voice-id", help="ElevenLabs voice id (or ELEVENLABS_VOICE_ID)")
    sp.add_argument("--model", default="eleven_multilingual_v2")
    sp.add_argument("--speed", type=float, default=1.0)
    sp.add_argument("--stability", type=float, default=0.5)
    sp.add_argument("--similarity", type=float, default=0.8)
    sp.add_argument("--style", type=float, default=0.15)
    sp.add_argument("--only", nargs="*", help="regenerate only these line ids")

    sp = add("whisper", cmd_whisper, "transcribe audio with word timings and check each VO line against the script")
    sp.add_argument("audio", nargs="+")
    sp.add_argument("--expect", help='JSON object {"<file stem>": "expected line"} to diff against')
    sp.add_argument("--model", default="large-v3-turbo")
    sp.add_argument("--device", default="auto")
    sp.add_argument("--compute-type", default="default")
    sp.add_argument("--language", default="en")
    sp.add_argument("--offline", action="store_true", help="only use a locally cached model")

    sp = add("deliver", cmd_deliver, "CRF master, size-capped 2-pass social copy and stills")
    sp.add_argument("video")
    sp.add_argument("--audio", help="final mix WAV")
    sp.add_argument("--outdir", required=True)
    sp.add_argument("--name", default="reel")
    sp.add_argument("--max-mb", type=float, default=60.0)
    sp.add_argument("--stills", nargs="*", help="still times in seconds")
    sp.add_argument("--crf", type=int, default=15)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    query = {"command": args.command, "argv": list(argv if argv is not None else sys.argv[1:])}
    try:
        data = args.fn(args)
        warnings = data.pop("warnings", []) if isinstance(data, dict) else []
        payload = result_envelope(ok=True, source_name=SOURCE_NAME, source_url=SOURCE_URL, query=query, data=data, warnings=warnings)
        code = 0
    except SkillError as exc:
        payload = result_envelope(ok=False, source_name=SOURCE_NAME, source_url=SOURCE_URL, query=query, data=None, blocked=exc.exit_code == 4,
                                  error={"code": exc.exit_code, "type": exc.error_code, "message": str(exc)})
        code = exc.exit_code
    except KeyboardInterrupt:
        return 130
    if args.json or code:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        data = dict(payload["data"])
        data["warnings"] = payload["warnings"]
        human(args.command, data)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
