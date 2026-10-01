"""Headless-Chromium frame capture for canvas reels (Playwright, Python).

The project page must expose `window.__ready` (a promise) and an async
`window.renderAt(t)` that paints the frame for time t into the first <canvas>.
The starter template in assets/template does this.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import functools
import hashlib
import http.server
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

from reels_common import InputError, MissingDependency, SkillError, need_tool, run

GRAB = "async (t) => { await window.renderAt(t); return document.querySelector('canvas').toDataURL('image/png'); }"
SYSTEM_BROWSERS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "chrome")
CHROME_ARGS = ["--disable-gpu-vsync", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows"]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - silence per-request logs
        pass


@contextlib.contextmanager
def serve(root: Path):
    """Serve the project over loopback HTTP (file:// breaks fetch and fonts)."""
    handler = functools.partial(_Quiet, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{httpd.server_address[1]}"  # loopback only
    finally:
        httpd.shutdown()
        httpd.server_close()


def _playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise MissingDependency("playwright is not installed: pip install playwright") from exc
    return async_playwright


async def launch(pw):
    """Playwright's bundled Chromium, else REELS_CHROMIUM, else a system Chrome/Chromium."""
    explicit = os.environ.get("REELS_CHROMIUM")
    if not explicit:
        try:
            return await pw.chromium.launch(args=CHROME_ARGS)
        except Exception:  # bundled browser not installed; fall back to a system one
            pass
    last: Exception | None = None
    for candidate in [explicit] + [shutil.which(n) for n in SYSTEM_BROWSERS]:
        if candidate and Path(candidate).exists():
            try:
                return await pw.chromium.launch(executable_path=candidate, args=CHROME_ARGS)
            except Exception as exc:  # try the next one
                last = exc
    detail = str(last).splitlines()[0] if last else ""
    if "ProcessSingleton" in detail:
        raise SkillError("Chromium could not create its profile: point TMPDIR at a local POSIX filesystem (not NTFS/exFAT/SMB)")
    raise MissingDependency("no Chromium found: run `python -m playwright install chromium` or set REELS_CHROMIUM" + (f" ({detail})" if detail else ""))


def page_query(aspect: str, scale: float, fps: int, samples: int = 1, fast: int = 1, grain: float | None = None, extra: str = "") -> str:
    q = {"capture": 1, "aspect": aspect, "scale": scale, "fps": fps, "samples": samples, "fast": fast}
    if grain is not None:
        q["grain"] = grain
    s = urlencode(q)
    return s + ("&" + extra.lstrip("&?") if extra else "")


async def open_page(browser, url: str, timeout: float = 60.0):
    page = await browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"{m.text} ({m.location.get('url', '')})") if m.type == "error" else None)
    page.set_default_timeout(timeout * 1000)
    await page.goto(url)
    try:
        await page.wait_for_function("window.__ready !== undefined", timeout=timeout * 1000)
        await page.evaluate("window.__ready")
    except Exception as exc:
        raise SkillError(f"page never became ready ({'; '.join(errors) or str(exc).splitlines()[0]})") from exc
    if errors:
        raise SkillError("page error: " + "; ".join(errors[:3]))
    page._reel_errors = errors  # type: ignore[attr-defined]
    return page


async def grab(page, t: float) -> bytes:
    url = await page.evaluate(GRAB, t)
    errors = getattr(page, "_reel_errors", [])
    if errors:
        raise SkillError(f"page error at t={t}: " + "; ".join(errors[:3]))
    return base64.b64decode(url[url.index(",") + 1:])


def _project(project: str | Path, page: str) -> tuple[Path, str]:
    root = Path(project).resolve()
    if not (root / page).is_file():
        raise InputError(f"{root / page} not found (point at a project made with `cli.py init`)")
    return root, page


# ── Stills + contact sheet ───────────────────────────────────────────────

def shots(project: str, outdir: str, times: list[float], aspect: str, scale: float, page: str = "index.html", sheet: str | None = None, cols: int = 6, extra: str = "") -> dict:
    root, page = _project(project, page)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    async def go():
        async with _playwright()() as pw:
            browser = await launch(pw)
            try:
                with serve(root) as base:
                    p = await open_page(browser, f"{base}/{page}?{page_query(aspect, scale, 30, extra=extra)}")
                    info = await p.evaluate("window.REEL_INFO || null")
                    files = []
                    for t in times:
                        f = out / f"t{t:07.2f}.png"
                        f.write_bytes(await grab(p, t))
                        files.append(str(f))
                    return files, info
            finally:
                await browser.close()

    files, info = asyncio.run(go())
    result = {"stills": files, "reel": info}
    if sheet:
        result["sheet"] = contact_sheet(files, sheet, cols)
    return result


def contact_sheet(files: list[str], sheet: str, cols: int = 6, width: int = 270) -> str:
    """Tile stills in order with ffmpeg (no fonts needed; file names carry the times)."""
    need_tool("ffmpeg")
    if not files:
        raise InputError("no stills to tile")
    tmp = Path(sheet).with_suffix(".tiles")
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for i, f in enumerate(files):
            shutil.copyfile(f, tmp / f"{i:05d}.png")
        rows = (len(files) + cols - 1) // cols
        run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(tmp / "%05d.png"), "-vf",
             f"scale={width}:-2:flags=area,pad=iw+12:ih+12:6:6:color=0x222222,tile={cols}x{rows}:color=0x222222",
             "-frames:v", "1", str(sheet)])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return str(sheet)


# ── Parallel frame-exact render ─────────────────────────────────────────

async def _render_range(pages, ff, start: int, stop: int, fps: int, log_every: int, t0: float, total: int):
    buf: dict[int, bytes] = {}
    state = {"next": start, "written": 0}
    workers = len(pages)

    def flush():
        while state["next"] in buf:
            ff.stdin.write(buf.pop(state["next"]))
            state["next"] += 1
            state["written"] += 1
            if state["written"] % log_every == 0:
                el = time.time() - t0
                print(f"frame {state['next']}/{total}  {state['written'] / el:.1f} fps", file=sys.stderr, flush=True)

    async def worker(w, page):
        for f in range(start + w, stop, workers):
            while f - state["next"] > workers * 6:  # bounded reorder buffer
                await asyncio.sleep(0.01)
            buf[f] = await grab(page, f / fps)
            flush()

    await asyncio.gather(*(worker(w, p) for w, p in enumerate(pages)))
    flush()
    return state["written"]


def _encoder(out: Path, fps: int, crf: int) -> subprocess.Popen:
    need_tool("ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
         "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv444p", str(out)],
        stdin=subprocess.PIPE,
    )


def render(project: str, out: str, start: int | None, stop: int | None, fps: int, workers: int, aspect: str, scale: float, samples: int, fast: int, grain: float | None, chunk_frames: int, page: str = "index.html", crf: int = 4, resume: bool = False, extra: str = "") -> dict:
    """Render frames [start, stop) to a near-lossless x264 intermediate, in chunks."""
    root, page = _project(project, page)
    out_path = Path(out)
    if not 1 <= workers <= 32:
        raise InputError("workers must be 1..32")
    if fps not in (24, 25, 30, 50, 60):
        raise InputError("fps must be one of 24, 25, 30, 50, 60")

    async def go():
        async with _playwright()() as pw:
            browser = await launch(pw)
            try:
                with serve(root) as base:
                    url = f"{base}/{page}?{page_query(aspect, scale, fps, samples, fast, grain, extra)}"
                    pages = await asyncio.gather(*(open_page(browser, url) for _ in range(workers)))
                    info = await pages[0].evaluate("window.REEL_INFO || null")
                    if not info or "duration" not in info:
                        raise SkillError("page does not expose window.REEL_INFO.duration")
                    if info["width"] % 2 or info["height"] % 2:
                        raise InputError(f"canvas {info['width']}x{info['height']} must have even dimensions for x264; adjust --scale")
                    a = 0 if start is None else start
                    b = int(round(info["duration"] * fps)) if stop is None else stop
                    if not 0 <= a < b:
                        raise InputError(f"empty frame range {a}..{b}")
                    # Throwaway frame per page: a page's first frame can differ by a few AA pixels.
                    await asyncio.gather(*(grab(p, a / fps) for p in pages))
                    size = chunk_frames if chunk_frames > 0 else b - a
                    chunks = []
                    t0 = time.time()
                    written = 0
                    for c0 in range(a, b, size):
                        c1 = min(b, c0 + size)
                        seg = out_path if size >= b - a else out_path.with_name(f"{out_path.stem}.f{c0:06d}-{c1:06d}{out_path.suffix}")
                        chunks.append(seg)
                        if resume and seg.is_file() and seg.stat().st_size > 0 and seg != out_path:
                            continue
                        ff = _encoder(seg, fps, crf)
                        try:
                            written += await _render_range(pages, ff, c0, c1, fps, max(30, fps * 2), t0, b)
                        finally:
                            ff.stdin.close()
                            if ff.wait() != 0:
                                raise SkillError(f"ffmpeg failed writing {seg}")
                    return info, a, b, chunks, written, time.time() - t0
            finally:
                await browser.close()

    info, a, b, chunks, written, elapsed = asyncio.run(go())
    if len(chunks) > 1:
        lst = out_path.with_suffix(".concat.txt")
        lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in chunks), encoding="utf-8")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_path)])
        lst.unlink(missing_ok=True)
    return {
        "out": str(out_path),
        "frames": [a, b],
        "fps": fps,
        "size": [info["width"], info["height"]],
        "chunks": [str(c) for c in chunks] if len(chunks) > 1 else [],
        "rendered_frames": written,
        "seconds": round(elapsed, 1),
        "render_fps": round(written / elapsed, 1) if elapsed > 0 else None,
    }


# ── Determinism check ───────────────────────────────────────────────────

def determinism(project: str, times: list[float], pages_n: int, history: list[float], aspect: str, scale: float, page: str = "index.html", dump: str | None = None, extra: str = "") -> dict:
    """Render the same t on several pages after different previous frames; hashes must match."""
    root, page = _project(project, page)
    if dump:
        Path(dump).mkdir(parents=True, exist_ok=True)

    async def go():
        async with _playwright()() as pw:
            browser = await launch(pw)
            try:
                with serve(root) as base:
                    url = f"{base}/{page}?{page_query(aspect, scale, 30, extra=extra)}"
                    pages = await asyncio.gather(*(open_page(browser, url) for _ in range(pages_n)))
                    await asyncio.gather(*(grab(p, 0) for p in pages))  # ignore each page's first frame
                    report = []
                    for t in times:
                        seen: dict[str, list[str]] = {}

                        async def one(w, p, t=t, seen=seen):
                            for h in history:
                                await grab(p, h)
                                png = await grab(p, t)
                                digest = hashlib.md5(png).hexdigest()[:12]
                                if digest not in seen and dump:
                                    Path(dump, f"t{t:.2f}-{digest}.png").write_bytes(png)
                                seen.setdefault(digest, []).append(f"p{w}/after{h}")

                        await asyncio.gather(*(one(w, p) for w, p in enumerate(pages)))
                        report.append({"t": t, "distinct": len(seen), "hashes": seen})
                    return report
            finally:
                await browser.close()

    report = asyncio.run(go())
    bad = [r["t"] for r in report if r["distinct"] > 1]
    return {"deterministic": not bad, "nondeterministic_times": bad, "pages": pages_n, "history": history, "times": report}
