# Render and QA

## Engine contract

- A frame is `composite(ctx, t)`: paint everything from nothing for time `t`. No `Math.random()`, no
  `Date.now()`, no `performance.now()`, no state that survives between frames. Use `FF.hash(n)` and
  `FF.noise(x, seed)` for anything that should look random.
- Logical coordinates are `FF.W × FF.H` (set by `?aspect=`). The canvas can be any size (`?scale=`); the
  engine sets the transform. Keep `?scale` producing even pixel sizes (the template rounds for you).
- `samples > 1` gives motion blur by averaging sub-frames inside a 180° shutter. Use `--samples 1
  --fast 3` and list whip pans and slams in `FF_REEL.FAST`, so only those spans pay for blur.
- `window.renderAt(t)` is async on purpose: scenes that need footage frames or images await them before
  drawing.

## Stills and contact sheets

`cli.py shots <project> <outdir> 0:60:1 --sheet sheet.png --scale 0.5` renders stills on one page and
tiles them with ffmpeg (file names carry the times). Review a full sheet before every full render: check
reading time, safe margins, colour discipline and that every line has its own image.

## Chunked parallel render

`cli.py render` opens N headless pages, renders frames round-robin, and pipes PNGs in order through a
bounded reorder buffer into x264 (CRF 4, yuv444p): a near-lossless intermediate that `deliver` encodes
from. Chunks default to 1,800 frames (`--chunk-frames`); `--resume` skips chunks that already exist; the
chunks are concatenated with `-c copy` at the end.

- Each page renders one throwaway frame first: a page's very first frame can differ by a few
  anti-aliased pixels.
- Throughput depends on the scene. Text-only 9:16 at 30 fps renders far faster than real time on a
  desktop CPU; WebGL + footage + supersampling can drop to ~5 fps. Do a 10-second test chunk first and
  size chunks so each finishes in a few minutes.
- Quick previews: `--scale 0.333` (360 px wide for 9:16) and fewer workers.

## Determinism check (before any full render)

`cli.py determinism <project> --t 2.1 14 33.5 --pages 4` renders each test time on several pages after
different previous frames and compares hashes. One hash per time means frames do not depend on history
or on which worker rendered them. Pick times inside your heaviest scenes. `--dump dir` writes one PNG
per distinct hash so you can diff them.

Then render one range twice with different `--workers` and compare with `cli.py vdiff a.mkv b.mkv`.

## Flicker check (after every render)

`cli.py flicker master.mkv` downsamples to luma and flags **single-frame spikes**: a frame that differs
from both neighbours while the neighbours agree (a pop-in, a missing mesh, a 1-frame flash). Hard cuts
show up as one-sided steps (`hard_cuts`) and are fine. `luma_bumps` lists brightness bends such as eased
flashes; confirm they are intended. Inspect every spike as a strip of consecutive frames
(`shots` at 1/30 s steps) before trusting or dismissing it.

## WebGL scenes (Three.js or raw WebGL) composited into the 2D canvas

Problems seen in parallel headless renders and their fixes:

- **Whole meshes or the background vanish on random frames.** `drawImage(glCanvas)` copied a buffer the
  GPU had not finished. Call `renderer.getContext().finish()` right after `renderer.render()` and before
  `drawImage`. Cost is negligible.
- **Thin lines and edges differ between pages.** The MSAA resolve was nondeterministic. Use
  `antialias: false` with `renderer.setPixelRatio(2)` (supersampling), then draw down with
  `imageSmoothingQuality = 'high'`.
- **A blank grey sky on one page.** Equirectangular `scene.background` textures convert lazily. Use a
  vertex-coloured sky-dome mesh instead.
- **Physics without drift:** integrate from rest with a fixed `dt` up to `t` every frame (a pure function
  of `t`) rather than stepping state between frames.
- Launch flags: the CLI uses Chromium defaults; if you need GPU rasterisation, test determinism again
  after changing flags.

## Footage inside the canvas

- Pre-cut each shot to graded JPEG frames at the project fps with ffmpeg (crop, grade with
  `eq`/`colorbalance`, `fps=30`). Before drawing frame `t`, load the frames for `t ± 1 frame`.
- Load frames with `fetch` + `createImageBitmap`, **not** `Image.decode()`: `decode()` can never resolve
  in background headless tabs, which hangs parallel renders.
- Find cuts in source clips with `ffmpeg -vf scdet=threshold=12`; check the first and last frame of every
  shot for burned-in text or UI.
- HUD trackers over footage: hand-key positions from a gridded frame sheet (ffmpeg `drawgrid`, every 15
  frames) and interpolate linearly.
- Keep type readable on footage with dark scrims (gradients) under the text.
