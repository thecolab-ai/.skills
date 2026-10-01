"""Video QA and delivery: flicker detector, frame diff, social copy + master + stills."""

from __future__ import annotations

import subprocess
from pathlib import Path

from reels_common import InputError, SkillError, need_numpy, need_tool, probe, run


def _frames(src: str, w: int, h: int):
    np = need_numpy()
    need_tool("ffmpeg")
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", src, "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            b = p.stdout.read(w * h)
            if len(b) < w * h:
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w).astype(np.int16)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def flicker(src: str, threshold: float = 2.0, luma_jump: float = 3.0, start_frame: int = 0) -> dict:
    """Flag single-frame spikes: a frame differs from BOTH neighbours while they agree.

    Hard cuts show up as one-sided steps and are not flagged. Inspect every flag
    in a strip of consecutive frames before trusting or dismissing it.
    """
    np = need_numpy()
    info = probe(src)
    fps = info.get("fps") or 30.0
    fr = list(_frames(src, 480, 270))
    n = len(fr)
    if n < 3:
        raise InputError("need at least 3 frames")
    y = np.array([f.mean() for f in fr])
    ad = lambda a, b: float(np.abs(a - b).mean())  # noqa: E731
    d = [0.0] + [ad(fr[i], fr[i - 1]) for i in range(1, n)]
    flags, bumps = [], []
    for i in range(1, n - 1):
        skip = ad(fr[i + 1], fr[i - 1])
        spike = min(d[i], d[i + 1]) - skip
        dy = float(y[i] - 0.5 * (y[i - 1] + y[i + 1]))
        f = i + start_frame
        row = {"frame": f, "t": round(f / fps, 3), "luma": round(float(y[i]), 1), "luma_jump": round(dy, 2), "diff_prev": round(d[i], 2), "diff_next": round(d[i + 1], 2), "diff_skip": round(skip, 2), "spike": round(spike, 2)}
        if spike > threshold:
            flags.append(row)
        elif abs(dy) > luma_jump:
            bumps.append(row)  # brightness bends: eased flashes land here; check they are intended
    steps = [{"frame": i + start_frame, "t": round((i + start_frame) / fps, 3), "diff": round(d[i], 2)} for i in range(1, n) if d[i] > 12]
    return {"file": src, "frames": n, "fps": fps, "threshold": threshold, "flagged": flags, "luma_bumps": bumps[:200], "hard_cuts": steps[:200]}


def vdiff(a: str, b: str, px_threshold: int = 50, delta: int = 8, start_frame: int = 0) -> dict:
    """Per-frame comparison of two renders of the same range."""
    np = need_numpy()
    ia, ib = probe(a), probe(b)
    if (ia.get("width"), ia.get("height")) != (ib.get("width"), ib.get("height")):
        raise InputError("videos have different sizes")
    w, h = ia["width"], ia["height"]
    bad = []
    n = 0
    for i, (x, y) in enumerate(zip(_frames(a, w, h), _frames(b, w, h))):
        n += 1
        diff = np.abs(x - y)
        px = int((diff > delta).sum())
        if px > px_threshold:
            ys, xs = np.nonzero(diff > delta)
            bad.append({"frame": i + start_frame, "pixels": px, "max": int(diff.max()), "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]})
    return {"a": a, "b": b, "frames": n, "differing_frames": len(bad), "frames_detail": bad[:500], "identical": not bad}


def deliver(video: str, audio: str | None, outdir: str, name: str, max_mb: float = 60.0, stills: list[float] | None = None, master_crf: int = 15, audio_kbps: int = 192, max_video_kbps: int = 12000) -> dict:
    """CRF master, a 2-pass size-capped social copy, and stills."""
    need_tool("ffmpeg")
    info = probe(video)
    dur = info["duration"]
    if dur <= 0:
        raise InputError("video has no duration")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    a_in = ["-i", audio] if audio else []
    a_map = ["-map", "0:v:0"] + (["-map", "1:a:0", "-shortest"] if audio else [])
    master = out / f"{name}_master.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", video, *a_in, *a_map, "-c:v", "libx264", "-preset", "slow", "-crf", str(master_crf), "-pix_fmt", "yuv420p",
         *(["-c:a", "aac", "-b:a", "320k", "-ar", "48000"] if audio else []), "-movflags", "+faststart", str(master)])
    social = out / f"{name}_social.mp4"
    log = out / f".{name}_2pass"
    budget_kbits = max_mb * 8 * 1024 * 0.94
    attempts = []
    factor = 1.0
    for _ in range(3):
        vk = int(min(max_video_kbps, (budget_kbits / dur - (audio_kbps if audio else 0)) * factor))
        if vk < 300:
            raise InputError(f"{max_mb} MB is too small for {dur:.0f}s of video")
        common = ["-c:v", "libx264", "-preset", "slow", "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.5)}k", "-bufsize", f"{vk * 2}k", "-pix_fmt", "yuv420p", "-passlogfile", str(log)]
        run(["ffmpeg", "-v", "error", "-y", "-i", video, "-map", "0:v:0", *common, "-pass", "1", "-an", "-f", "null", "-"])
        run(["ffmpeg", "-v", "error", "-y", "-i", video, *a_in, *a_map, *common, "-pass", "2",
             *(["-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ar", "48000"] if audio else []), "-movflags", "+faststart", str(social)])
        mb = social.stat().st_size / 1024 / 1024
        attempts.append({"video_kbps": vk, "mb": round(mb, 2)})
        if mb <= max_mb:
            break
        factor *= 0.85
    for p in out.glob(f".{name}_2pass*"):
        p.unlink(missing_ok=True)
    if social.stat().st_size / 1024 / 1024 > max_mb:
        raise SkillError(f"social copy is still over {max_mb} MB after 3 attempts")
    still_files = []
    for t in stills or []:
        if not 0 <= t < dur:
            raise InputError(f"still time {t} is outside 0..{dur:.2f}")
        f = out / f"{name}_still_{t:06.2f}.png"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", str(f)])
        still_files.append(str(f))
    result = {
        "master": {"path": str(master), "mb": round(master.stat().st_size / 1024 / 1024, 2), "crf": master_crf},
        "social": {"path": str(social), "mb": round(social.stat().st_size / 1024 / 1024, 2), "limit_mb": max_mb, "attempts": attempts},
        "stills": still_files,
        "duration": round(dur, 3),
        "size": [info.get("width"), info.get("height")],
    }
    if audio:
        from reels_audio import measure

        result["social"]["loudness"] = measure(str(social))
    return result
