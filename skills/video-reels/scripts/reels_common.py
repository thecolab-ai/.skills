"""Shared errors and small process helpers for the video-reels CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class SkillError(Exception):
    exit_code = 5
    error_code = "tool_failed"


class InputError(SkillError):
    exit_code = 2
    error_code = "invalid_input"


class MissingDependency(SkillError):
    """A local tool or optional Python package is not installed."""

    exit_code = 3
    error_code = "dependency_missing"


class MissingCredential(SkillError):
    exit_code = 3
    error_code = "missing_configuration"


class Blocked(SkillError):
    exit_code = 4
    error_code = "rate_limited"


class Upstream(SkillError):
    exit_code = 5
    error_code = "upstream_unavailable"


def need_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MissingDependency(f"{name} is not installed or not on PATH")
    return path


def need_numpy():
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        raise MissingDependency("numpy is not installed: pip install numpy") from exc
    return numpy


def run(cmd: list[str], *, capture: bool = True, timeout: int | None = None, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a local tool; turn a non-zero exit into a clean SkillError."""
    need_tool(cmd[0])
    try:
        done = subprocess.run(cmd, capture_output=capture, timeout=timeout, input=input_bytes, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"{cmd[0]} did not finish within {timeout}s") from exc
    if done.returncode != 0:
        tail = (done.stderr or b"").decode(errors="replace").strip().splitlines()[-3:]
        raise SkillError(f"{cmd[0]} failed (exit {done.returncode}): {' | '.join(tail)}")
    return done


def probe(path: str | Path) -> dict:
    """Duration, size and frame rate of a media file via ffprobe."""
    if not Path(path).is_file():
        raise InputError(f"file not found: {path}")
    done = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate,sample_rate", "-of", "json", str(path)])
    info = json.loads(done.stdout)
    out = {"duration": float(info.get("format", {}).get("duration") or 0.0)}
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video" and "width" not in out:
            num, _, den = str(stream.get("r_frame_rate", "30/1")).partition("/")
            out.update(width=int(stream["width"]), height=int(stream["height"]), fps=float(num) / float(den or 1))
        if stream.get("codec_type") == "audio" and "sample_rate" not in out:
            out["sample_rate"] = int(stream.get("sample_rate") or 0)
    return out


def parse_times(spec: list[str]) -> list[float]:
    """Accept '12.5' or 'a:b:step' ranges."""
    times: list[float] = []
    for item in spec:
        for part in str(item).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                if ":" in part:
                    a, b, step = (float(x) for x in part.split(":"))
                    if step <= 0:
                        raise ValueError
                    x = a
                    while x <= b + 1e-9:
                        times.append(round(x, 3))
                        x += step
                else:
                    times.append(float(part))
            except ValueError as exc:
                raise InputError(f"bad time value: {part!r} (use 12.5 or start:end:step)") from exc
    if not times:
        raise InputError("no times given")
    return times
