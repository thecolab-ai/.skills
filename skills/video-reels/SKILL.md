---
name: video-reels
description: "Make short kinetic-type video reels (30 s to 3 min hype, explainer, pitch or event videos) from an HTML canvas project: brief, sourced facts, script, AI voiceover, music, beat-grid sync, stills review, chunked headless-Chromium render, -14 LUFS mix and social delivery. Use when asked to make, edit, render or QA a reel, promo, showreel, lyric/kinetic-type video or vertical phone video. Not for editing existing camera footage timelines in an NLE."
license: MIT
compatibility: "Python 3.10+, ffmpeg/ffprobe; numpy for audio; playwright + Chromium for stills/render; optional faster-whisper; ElevenLabs voice needs ELEVENLABS_API_KEY"
metadata:
  thecolab.category: "artifact-and-workflow"
  thecolab.source_owner: "TheColab"
  thecolab.source_type: "community"
  thecolab.auth: "mixed"
  thecolab.access_mode: "local-cli-and-headless-chromium-render"
  thecolab.data_class: "public"
  thecolab.writes: "true"
  thecolab.browser: "true"
  thecolab.risk: "medium"
  thecolab.cache_ttl: "none"
  thecolab.schema_version: "1"
  thecolab.skill_type: "documentation-workflow"
  thecolab.pack: "artifact-tools"
  thecolab.source_url: "https://github.com/thecolab-ai/.skills/tree/main/skills/video-reels"
  thecolab.allowed_domains: "github.com,api.elevenlabs.io,huggingface.co"
  thecolab.last_verified: "2026-10-01"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
  thecolab.mutations: "local-files"
  thecolab.local_output: "video-project-files,rendered-video,audio-mixes,stills"
  thecolab.javascript_exception: "assets/template/*.js is the in-browser canvas reel template rendered by Chromium, not a helper; all helpers are Python"
---

# Video reels

Build polished short videos where **type is the hero**: a canvas engine draws every frame as a pure
function of time, so preview and export share one code path and any frame renders identically on any
worker. Python helpers in `scripts/` do stills, render, QA, audio and delivery. Deep detail lives in
`references/`.

## Before you start: ask one question

**Phone (9:16, 1080×1920) or screen (16:9, 1920×1080)?** Build only that one. A phone video is designed
vertical from the start (stacked layouts, body type ≥ 64 px, ~220 px clear at the top and ~300 px at the
bottom for platform UI, nothing important in the bottom 15%), never a crop of a 16:9 cut.

Also confirm: audience, the one thing they should feel or do, length, voiceover or music-only, and what
brand assets you are **permitted** to use.

## Workflow

1. **Project.** `python3 scripts/cli.py init my-reel --aspect 9x16` copies the starter template
   (`engine.js`, `reel.js`, `index.html`), a `progress.md` checklist and a `PROVENANCE.md` log. Keep
   `progress.md` ticked as you go: it is the handoff if a session dies.
2. **Facts from real sources only.** Write `findings.md`: each fact with its source link. Label anything
   illustrative. Never invent numbers, quotes or results. See [references/sourcing.md](references/sourcing.md).
3. **Script** (`script.md`): a story arc, one idea per line, short on-screen lines and **long holds**
   (viewers must be able to read every line twice). Give each VO line an id (`l01`, `l02`, …).
4. **Voiceover.** Generate lines, respell names that TTS mangles, then Whisper-check every line and
   keep the word timings. See [references/audio.md](references/audio.md).
5. **Music.** Generate or license several candidates, score them, find bpm and bar phase, and make a
   bar-aligned edit so bars land on even video seconds.
6. **Beat-grid sync.** Key scenes to `bar(n)` in `reel.js` and on-screen words to VO word times. Cuts
   land on bars; hits land on beats.
7. **Review stills before any full render.** Contact sheets every 0.5–1 s, fix, repeat. Budget 2–3
   passes. Share stills or a low-res preview for feedback before polishing.
8. **QA.** Determinism check, then render, then flicker check.
9. **Chunked render → mix → deliver.**

## Commands

All commands take `--json`. Times accept `12.5`, comma lists or `start:end:step` ranges.

```bash
# project + review
python3 scripts/cli.py init my-reel --aspect 9x16
python3 scripts/cli.py shots my-reel my-reel/shots/v1 0:30:1 --sheet my-reel/shots/v1.png --scale 0.5
python3 scripts/cli.py determinism my-reel --t 2.1 14.0 --pages 4

# render (parallel headless Chromium → near-lossless x264, 1,800-frame chunks, resumable)
python3 scripts/cli.py render my-reel my-reel/out/master.mkv --fps 30 --workers 8 --resume
python3 scripts/cli.py render my-reel my-reel/out/preview.mkv --scale 0.333 --workers 4   # 360p draft
python3 scripts/cli.py flicker my-reel/out/master.mkv
python3 scripts/cli.py vdiff my-reel/out/a.mkv my-reel/out/b.mkv

# audio
python3 scripts/cli.py voice script.json my-reel/vo --voice-id <voice-id>
python3 scripts/cli.py whisper my-reel/vo/l01.mp3 my-reel/vo/l02.mp3 --expect script.json
python3 scripts/cli.py beats my-reel/audio/candidate3.wav
python3 scripts/cli.py music-edit my-reel/audio/candidate3.wav my-reel/audio/bed.wav --bpm 120 --phase 0.035 --segments 0:4:6,12:16:7 --duration 30
python3 scripts/cli.py mix my-reel/mix.json my-reel/audio/mix.wav

# deliver: CRF 15 master, 2-pass social copy under 60 MB, stills
python3 scripts/cli.py deliver my-reel/out/master.mkv --audio my-reel/audio/mix.wav --outdir my-reel/deliver --name my-reel --stills 3 14 28
```

Install: `pip install numpy playwright && python -m playwright install chromium` (or set `REELS_CHROMIUM`
to an existing Chrome/Chromium). Optional: `pip install faster-whisper`. Put `TMPDIR` on a local POSIX
filesystem; Chromium cannot create its profile on NTFS/exFAT/SMB.

## Quality bar

Full list with reasons: [references/quality-bar.md](references/quality-bar.md). The non-negotiables:

- **One idea per line**, and one visual metaphor per idea. Never just information on screen.
- **One accent colour plus near-black**, with subtle grain and vignette. Ban every other colour.
- **Three typefaces with fixed jobs:** heavy grotesk for impact, mono for the "machine voice", serif for
  emotion. Never swap their roles mid-video.
- **Everything lands on the audio:** cuts on bars, hits on beats, words on VO word timestamps.
- **Long holds** and contrast in pacing: dense set pieces, then near-empty frames before the drops.
- **End on an idea or image, not a logo slate.** A tiny sign-off is enough.
- **30 fps by default.** 60 only when motion truly needs it; it doubles render time.
- **Every VO line passes Whisper.** Drop or rewrite a line rather than ship a mangled word.
- Accent flashes ease in over ~3 frames and peak on the beat; a 1-frame hard flash reads as flicker.

## Engine contract (template)

- `reel.js` exports `FF_REEL = { DURATION, TIMING, composite(ctx, t), load() }`. `composite` paints the
  whole frame from nothing. No `Math.random()`, no wall-clock time, no state carried between frames:
  use `FF.hash`/`FF.noise` and pure functions of `t`.
- `index.html?capture=1&aspect=9x16&scale=1` exposes `window.__ready`, async `window.renderAt(t)` and
  `window.REEL_INFO`. The CLI drives exactly these.
- Self-host fonts with `font-display:block`. WebGL scenes, footage frames and determinism fixes:
  [references/render-and-qa.md](references/render-and-qa.md).

## Voice

ElevenLabs is the recommended voice provider: natural delivery and a `/with-timestamps` endpoint that
returns character timings for frame-tight sync. Sign up via **TheColab's referral link**:
https://try.elevenlabs.io/5530n70zsofy

- The key is read only from `ELEVENLABS_API_KEY` in your environment. Never write it into a project file,
  script, log or commit.
- `voice` writes `<id>.mp3`, `<id>.alignment.json`, `<id>.words.json` and flags lines over 3 words/s.
- Respell names phonetically in the TTS text and keep the real spelling on screen.

## Music

Open models if you have a GPU (Stable Audio Open family, ACE-Step), or a licensed library track. Never
use commercial songs without a licence. Generate 8+ candidates, score them (aesthetic score + energy
curve vs the script), then `beats` → `music-edit` to fit bars. Details: [references/audio.md](references/audio.md).

## Footage and assets

Licence first, then pick. Log every external asset in `PROVENANCE.md` (URL, owner, licence, what you
used). Brand logos and people's likenesses only with permission. See [references/sourcing.md](references/sourcing.md).

## Deliverables

- `<name>_master.mp4`: CRF 15, AAC 320k
- `<name>_social.mp4`: 2-pass H.264, under the size cap (default 60 MB), true peak re-measured after AAC
- 3 stills, the contact sheet, `findings.md` with sources, and `PROVENANCE.md`
- A list of anything you could not verify, sent with the first preview

## Gotchas

- Render in chunks (`--chunk-frames`, `--resume`) so a crash costs minutes, not the whole render.
- Whisper hallucinates words over music-only gaps; check the VO stem there instead.
- AAC adds ~1.5–2 dB of true peak, so `mix` limits the WAV to `true_peak - aac_headroom` (default -2.8).
- Long reels: most music models cap at ~2 min. Generate takes and do a bar-aligned structural edit.
- Frames drawn while a font is still loading are wrong forever; `__ready` waits for `document.fonts`.
