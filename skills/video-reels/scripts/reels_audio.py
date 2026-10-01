"""Audio helpers: decode, beat grid, bar-aligned music edits, VO-ducked mix, loudness.

numpy + ffmpeg only. Every function is deterministic for the same input.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from reels_common import InputError, SkillError, need_numpy, need_tool, run

SR = 48000


def decode(path: str | Path, sr: int = SR, channels: int = 2):
    np = need_numpy()
    if not Path(path).is_file():
        raise InputError(f"audio file not found: {path}")
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", str(channels), "-ar", str(sr), "-f", "f32le", "-"]).stdout
    x = np.frombuffer(raw, np.float32).copy()
    return x.reshape(-1, channels) if channels > 1 else x


def write_wav(path: str | Path, x, sr: int = SR, subtype: str = "pcm_s24le") -> None:
    np = need_numpy()
    x = np.asarray(x, np.float32)
    channels = 1 if x.ndim == 1 else x.shape[1]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", str(channels), "-i", "-", "-c:a", subtype, str(path)], input_bytes=x.tobytes())


def db(g: float) -> float:
    return 10 ** (g / 20)


# ── Beat grid ────────────────────────────────────────────────────────────

def onset_envelope(y, sr: int, hop: int = 256, n_fft: int = 1024):
    """Log-magnitude spectral flux, normalised to 0..1."""
    np = need_numpy()
    if len(y) < n_fft * 2:
        raise InputError("audio is too short for beat analysis")
    window = np.hanning(n_fft).astype(np.float32)
    y = np.pad(y, (n_fft // 2, 0))  # centre frames: frame i describes time i * hop / sr
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop] * window
    mag = np.log1p(10 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(1)
    flux = np.concatenate([[0.0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, "same")  # remove slow loudness drift
    flux = np.maximum(flux, 0)
    peak = flux.max()
    return (flux / peak if peak > 0 else flux), mag


def _score(env, fps: float, bpm: float, duration: float, phase_step: float):
    np = need_numpy()
    period = 60.0 / bpm
    phases = np.arange(0, period, phase_step)
    beats = np.arange(0, duration - period, period)
    idx = ((phases[:, None] + beats[None, :]) * fps).astype(int)
    idx = np.clip(idx, 0, len(env) - 1)
    scores = env[idx].mean(1)
    k = int(scores.argmax())
    return float(scores[k]), float(phases[k])


def beat_grid(path: str | Path, bpm_min: float = 70, bpm_max: float = 180, beats_per_bar: int = 4, bpm: float | None = None, start: float = 0.0, end: float | None = None) -> dict:
    """Find bpm, beat phase and the first downbeat; return the bar grid."""
    np = need_numpy()
    sr = 22050
    y = decode(path, sr=sr, channels=1)
    full = len(y) / sr
    a = int(max(0.0, start) * sr)
    b = int((end if end else full) * sr)
    y = y[a:b]
    duration = len(y) / sr
    hop = 256
    fps = sr / hop
    env, mag = onset_envelope(y, sr, hop)
    if bpm:
        candidates = [(_score(env, fps, bpm, duration, 0.002), bpm)]
    else:
        if not 30 <= bpm_min < bpm_max <= 300:
            raise InputError("bpm range must sit within 30..300 and min < max")
        coarse = [(_score(env, fps, x, duration, 0.01), x) for x in np.arange(bpm_min, bpm_max, 0.5)]
        coarse.sort(key=lambda c: -c[0][0])
        candidates = []
        for (_, centre) in coarse[:3]:
            for x in np.arange(centre - 0.6, centre + 0.6, 0.02):
                candidates.append((_score(env, fps, float(x), duration, 0.002), float(x)))
        candidates.sort(key=lambda c: -c[0][0])
    (score, phase), best = candidates[0]
    period = 60.0 / best
    # Downbeat: the beat-in-bar position with the most low-frequency energy.
    low = mag[:, : max(2, int(150 / (sr / 1024)))].sum(1)
    strength = []
    for k in range(beats_per_bar):
        ts = np.arange(phase + k * period, duration - 0.05, period * beats_per_bar)
        idx = np.clip((ts * fps).astype(int), 0, len(low) - 1)
        strength.append(float(low[idx].mean()) if len(idx) else 0.0)
    top = max(strength) or 1.0
    k = int(np.argmax(strength))
    downbeat = start + phase + k * period
    bar = period * beats_per_bar
    bars = [round(t, 4) for t in np.arange(downbeat, start + duration, bar)]
    return {
        "file": str(path),
        "duration": round(full, 3),
        "bpm": round(best, 3),
        "beat_seconds": round(period, 5),
        "beat_phase": round(start + phase, 4),
        "beats_per_bar": beats_per_bar,
        "bar_seconds": round(bar, 5),
        "first_downbeat": round(downbeat, 4),
        "downbeat_confidence": [round(s / top, 2) for s in strength],
        "trim_to_align": round(downbeat % bar, 4),
        "bars": bars[:256],
        "score": round(score, 4),
        "alternatives": [{"bpm": round(c[1], 2), "phase": round(c[0][1], 3), "score": round(c[0][0], 4)} for c in candidates[1:6]],
        "note": "Trim trim_to_align seconds from the start (or start the music that much early) so bar n lands at n × bar_seconds in the video.",
    }


# ── Bar-aligned structural edit ──────────────────────────────────────────

def music_edit(src: str | Path, out: str | Path, bpm: float, phase: float, segments: list[tuple[float, int, int]], duration: float, beats_per_bar: int = 4, xfade: float = 0.025, fade_out: float = 1.75) -> dict:
    """Assemble (video_start_s, source_bar, n_bars) pieces with equal-power crossfades."""
    np = need_numpy()
    x = decode(src)
    bar = 60.0 / bpm * beats_per_bar
    n = int(duration * SR)
    outbuf = np.zeros((n + SR, 2), np.float32)
    xf = max(1, int(xfade * SR))
    ramp = (np.sin(np.linspace(0, np.pi / 2, xf)) ** 2)[:, None].astype(np.float32)
    placed = []
    for v0, b, nb in segments:
        s = int((phase + bar * b) * SR) - xf
        e = min(len(x), int((phase + bar * (b + nb)) * SR) + xf)
        if s < 0 or s >= len(x) or e <= s:
            raise InputError(f"segment source bar {b} (+{nb}) is outside the {len(x) / SR:.1f}s source")
        piece = x[s:e].copy()
        piece[:xf] *= ramp
        piece[-xf:] *= ramp[::-1]
        d = int(v0 * SR) - xf
        if d < 0:
            piece = piece[-d:]
            d = 0
        end = min(len(outbuf), d + len(piece))
        outbuf[d:end] += piece[: end - d]
        placed.append({"video_start": v0, "source_bar": b, "bars": nb, "source_seconds": [round(phase + bar * b, 3), round(phase + bar * (b + nb), 3)]})
    outbuf = outbuf[:n]
    t = np.arange(n) / SR
    gain = np.ones(n, np.float32)
    if fade_out > 0:
        m = t > duration - fade_out
        gain[m] = np.clip(1 - (t[m] - (duration - fade_out)) / fade_out, 0, 1) ** 2
    m = t < 0.05
    gain[m] *= t[m] / 0.05
    outbuf *= gain[:, None]
    write_wav(out, outbuf)
    return {"out": str(out), "duration": duration, "bar_seconds": round(bar, 5), "segments": placed}


def parse_segments(spec: str) -> list[tuple[float, int, int]]:
    segs = []
    for part in spec.split(","):
        try:
            v0, b, nb = part.split(":")
            segs.append((float(v0), int(b), int(nb)))
        except ValueError as exc:
            raise InputError(f"bad segment {part!r}; use video_start:source_bar:bars") from exc
    if not segs:
        raise InputError("no segments")
    return segs


# ── Mix ──────────────────────────────────────────────────────────────────

def _sliding_max(a, width: int):
    np = need_numpy()
    if width <= 1:
        return a
    pad = np.pad(a, (width // 2, width - width // 2 - 1), mode="edge")
    return np.lib.stride_tricks.sliding_window_view(pad, width).max(1)


def duck_curve(vo_mono, duck_db: float, threshold: float = 0.012, hold: float = 0.45, rate: int = 1000):
    """Gain curve (per sample) that dips music under VO and holds through word tails."""
    np = need_numpy()
    n = len(vo_mono)
    step = SR // rate
    m = (len(vo_mono) // step) * step
    env = np.abs(vo_mono[:m]).reshape(-1, step).mean(1)
    env = np.convolve(env, np.ones(50) / 50, "same")
    act = np.clip(env / threshold, 0, 1)
    act = _sliding_max(act, int(hold * rate))
    k = np.ones(120) / 120  # ~120 ms smoothing, both directions
    act = np.convolve(np.convolve(act, k, "same")[::-1], k, "same")[::-1]
    curve = 10 ** (duck_db * act / 20)
    return np.interp(np.arange(n) / SR, (np.arange(len(curve)) + 0.5) / rate, curve).astype(np.float32)


def impact(strength: float, seed: int = 1):
    """A soft synth low impact (no click: 4 ms attack)."""
    np = need_numpy()
    rng = np.random.default_rng(seed)
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    f = 55 * np.exp(-t * 3) + 32
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    noise = np.convolve(rng.standard_normal(n), np.ones(24) / 24, "same") * np.exp(-t * 14) * 0.6
    s = (body + noise) * np.clip(t / 0.004, 0, 1) * strength * 0.55
    return np.stack([s, s], 1).astype(np.float32)


def measure(path: str | Path) -> dict:
    """Integrated loudness (LUFS) and true peak (dBTP) via ffmpeg ebur128."""
    need_tool("ffmpeg")
    done = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    err = done.stderr.decode(errors="replace")
    summary = err[err.rfind("Summary:"):] if "Summary:" in err else err
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not i:
        raise SkillError("could not read loudness from ffmpeg ebur128")
    val = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else None  # noqa: E731
    return {"integrated_lufs": val(i), "true_peak_dbtp": val(tp)}


def loudnorm(src: str | Path, dst: str | Path, lufs: float, tp: float) -> dict:
    """Two-pass linear ffmpeg loudnorm, 48 kHz 24-bit out."""
    af = f"loudnorm=I={lufs}:TP={tp}:LRA=11"
    done = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af", af + ":print_format=json", "-f", "null", "-"])
    err = done.stderr.decode(errors="replace")
    try:
        j = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    except ValueError as exc:
        raise SkillError("ffmpeg loudnorm did not report measurements") from exc
    af2 = (
        f"{af}:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
        f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true"
    )
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af", af2, "-ar", str(SR), "-c:a", "pcm_s24le", str(dst)])
    return {"input_lufs": float(j["input_i"]), "input_true_peak": float(j["input_tp"]), "normalization_type": j.get("normalization_type")}


def mix(spec: dict, out: str | Path, base: Path) -> dict:
    """Build music + VO + SFX stems, duck music under VO, master to a loudness target.

    The WAV is limited to true_peak - aac_headroom because AAC encoding raises
    true peak by roughly 1.5-2 dB; `deliver` re-measures the encoded file.
    """
    np = need_numpy()
    try:
        duration = float(spec["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("mix spec needs a numeric duration") from exc
    if not 0 < duration <= 1800:
        raise InputError("duration must be between 0 and 1800 seconds")
    n = int(duration * SR)
    resolve = lambda p: str(p if Path(p).is_absolute() else base / p)  # noqa: E731
    at = lambda t: int(round(float(t) * SR))  # noqa: E731

    def add(dst, x, t, gain=1.0):
        s = at(t)
        if s < 0:
            x, s = x[-s:], 0
        e = min(n, s + len(x))
        if e > s:
            dst[s:e] += x[: e - s] * gain

    music = np.zeros((n, 2), np.float32)
    m = spec.get("music")
    if m:
        x = decode(resolve(m["path"]))
        trim = int(float(m.get("trim", 0)) * SR)
        add(music, x[trim:], float(m.get("at", 0)), db(float(m.get("gain_db", 0))))
        pts = sorted((float(t), float(g)) for t, g in m.get("automation", [])) or [(0.0, 0.0)]
        tt = np.arange(n) / SR
        music *= (10 ** (np.interp(tt, [p[0] for p in pts], [p[1] for p in pts]) / 20)).astype(np.float32)[:, None]
        fade_in = float(m.get("fade_in", 0.05))
        fade_out = float(m.get("fade_out", 1.5))
        g = np.ones(n, np.float32)
        if fade_in > 0:
            g *= np.clip(tt / fade_in, 0, 1)
        if fade_out > 0:
            g *= np.clip((duration - tt) / fade_out, 0, 1) ** 2
        music *= g[:, None]
    vo = np.zeros((n, 2), np.float32)
    for line in spec.get("vo", []):
        x = decode(resolve(line["path"]))
        x = x - np.convolve(x.mean(1), np.ones(600) / 600, "same")[:, None]  # gentle rumble cut (~80 Hz)
        add(vo, x, float(line["at"]), db(float(line.get("gain_db", 0))))
    sfx = np.zeros((n, 2), np.float32)
    for i, hit in enumerate(spec.get("sfx", [])):
        if hit.get("type", "impact") == "impact":
            add(sfx, impact(float(hit.get("strength", 0.6)), seed=i + 1), float(hit["at"]) - 0.02)
        elif hit.get("path"):
            add(sfx, decode(resolve(hit["path"])), float(hit["at"]), db(float(hit.get("gain_db", 0))))
    duck_db = float(spec.get("duck_db", -11))
    duck = duck_curve(vo.mean(1), duck_db) if spec.get("vo") else np.ones(n, np.float32)
    levels = spec.get("levels", {})
    music_bus = music * duck[:, None] * db(float(levels.get("music_db", -5)))
    sfx_bus = sfx * db(float(levels.get("sfx_db", -3)))
    vo_bus = vo * db(float(levels.get("vo_db", 0)))
    pre = music_bus + vo_bus + sfx_bus
    out = Path(out)
    stem_dir = out.with_suffix("")
    out.parent.mkdir(parents=True, exist_ok=True)
    pre_path = out.with_name(out.stem + ".pre.wav")
    write_wav(pre_path, pre, subtype="pcm_f32le")
    stems = {}
    if spec.get("write_stems", True):
        for name, bus in (("music", music_bus), ("vo", vo_bus), ("sfx", sfx_bus)):
            p = Path(f"{stem_dir}.{name}.wav")
            write_wav(p, bus, subtype="pcm_s16le")
            stems[name] = str(p)
    lufs = float(spec.get("lufs", -14))
    tp = float(spec.get("true_peak", -1.0))
    headroom = float(spec.get("aac_headroom", 1.8))
    norm = loudnorm(pre_path, out, lufs, tp - headroom)
    pre_path.unlink(missing_ok=True)
    meas = measure(out)
    warnings = []
    if meas["integrated_lufs"] is not None and abs(meas["integrated_lufs"] - lufs) > 1.0:
        warnings.append(f"integrated loudness {meas['integrated_lufs']} LUFS is more than 1 LU from {lufs}")
    if meas["true_peak_dbtp"] is not None and meas["true_peak_dbtp"] > tp:
        warnings.append(f"true peak {meas['true_peak_dbtp']} dBTP is above {tp}")
    return {
        "out": str(out),
        "duration": duration,
        "target_lufs": lufs,
        "target_true_peak": tp,
        "wav_true_peak_target": tp - headroom,
        "measured": meas,
        "loudnorm": norm,
        "duck_db": duck_db,
        "stems": stems,
        "warnings": warnings,
    }
