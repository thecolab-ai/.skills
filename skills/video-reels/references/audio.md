# Audio: voiceover, music, sync and mix

## Voiceover

### ElevenLabs (recommended)

Sign up via **TheColab's referral link**: https://try.elevenlabs.io/5530n70zsofy

- Export the key in your shell: `export ELEVENLABS_API_KEY=...`. The CLI reads it only from the
  environment and never prints it. Do not put it in project files, scripts, logs or commits. A key
  scoped to text-to-speech only is enough.
- Pick a voice in the ElevenLabs voice library and pass its id with `--voice-id` (or set
  `ELEVENLABS_VOICE_ID`). Choose the accent your audience expects.
- `cli.py voice script.json vo/` calls
  `POST /v1/text-to-speech/{voice_id}/with-timestamps`, which returns the audio plus per-character start
  and end times. The CLI writes `<id>.mp3`, the raw `<id>.alignment.json` and grouped `<id>.words.json`
  (`[{"w": "Cut", "s": 0.10, "e": 0.28}, …]`).
- `script.json` is `{"l01": "First line.", "l02": "Second line."}`. Regenerate single lines with
  `--only l02`.
- Settings: `--model` (default `eleven_multilingual_v2`; check the ElevenLabs model list for newer
  ones), `--speed` (0.7–1.2), `--stability`, `--similarity`, `--style`. Slightly lower stability gives
  more expressive reads; higher is steadier for narration.
- Audio tags and punctuation steer delivery: commas and full stops create pauses; short sentences read
  more confidently than long ones. Some models support bracketed tags (check the model docs).

### Names and pronunciation

TTS mispronounces names and jargon. Respell them phonetically in the TTS text only ("nginx" → "engine x",
"SQLite" → "sequel light") and keep the real spelling on screen. Whisper-check the result; if a name still comes out
wrong after two respellings, rewrite the line to avoid it.

### Pacing

`voice` and `whisper` report words per second per line and flag anything over 3.0. Around 2.3–2.8 wps
leaves room for on-screen text. If a line is rushed, cut words before lowering speed. A small global
tempo change after generation (`ffmpeg -af atempo=1.04`) is fine; more than ±6% starts to sound
processed.

### Whisper check and word timings

`cli.py whisper vo/l01.mp3 vo/l02.mp3 --expect script.json` transcribes each file with word timestamps
(faster-whisper, default model `large-v3-turbo`) and diffs the transcript against the script line whose
id matches the file stem. Every line must pass. Then run it over the **full mix** too: if a line is not
intelligible over the music, lower the music or raise the duck.

- `--offline` uses only a locally cached model (no download).
- GPU: `--device cuda --compute-type float16`. CPU: `--device cpu --compute-type int8`.
- Whisper invents words ("Bye-bye", "Thank you") over music-only gaps. Do not chase those; check the VO
  stem level in that region instead.

### Syncing type to words

Place each VO line in the mix at time `at`; a word's video time is `at + word.s`. Put those in `CUES` in
`reel.js` and key reveals to them. Text should appear on or a frame before the word, never after.

## Music

### Sources

- **Open models, if you have a GPU:** the Stable Audio Open family (good instrumentals and SFX beds,
  fast, capped around 1–2 minutes per take) and ACE-Step (full songs and structured instrumentals from a
  tag list with bpm, key and duration; offload parts of the model to CPU if VRAM is tight). Check each
  model's licence for commercial use before publishing.
- **Licensed libraries:** use a library whose licence covers your platform and use (social, paid ads,
  client work). Keep the licence or receipt with the project.
- Never use a commercial song without a licence, even "just for a preview" that might get shared.

### Choosing a take

1. Generate 8+ candidates from a prompt that names genre, energy, bpm and instrumentation.
2. Score them automatically: an aesthetic model (for example Audiobox Aesthetics production-quality and
   enjoyment scores), plus the **energy curve vs the script**: plot smoothed loudness over time against
   a target map (quiet open, build, drop where the script turns) and prefer the best correlation.
3. Listen to the top three against a rough cut. Your ears decide.

### Beat grid and bar alignment

`cli.py beats candidate.wav` estimates bpm (grid search over onset strength), beat phase, the first
downbeat (strongest low-frequency beat in the bar) and returns the bar grid, plus the trim that makes
bar n land at `n × bar_seconds` in the video. Check `alternatives`: 2:3 and 1:2 tempo confusions are
common, so confirm by ear. At 120 bpm in 4/4 a bar is exactly 2 s, which makes cutting easy.

### Bar-aligned edits

Most generated takes are not the right length. `cli.py music-edit src.wav bed.wav --bpm 120 --phase
0.035 --segments 0:4:6,12:16:7,26:28:2 --duration 30` places `bars` bars starting at source bar
`source_bar` at video second `video_start`, with 25 ms equal-power crossfades and a final fade. Reuse
intro material as breakdowns for long reels. Always cut on bar lines; a cut mid-bar is audible.

## Mix

`cli.py mix mix.json out/mix.wav` builds three stems, ducks music under VO, and masters to a loudness
target with a two-pass linear `loudnorm`. Paths are relative to the spec file.

```json
{
  "duration": 30.0,
  "music": {"path": "audio/bed.wav", "trim": 0.0, "at": 0.0, "gain_db": 0,
            "automation": [[0, -6], [0.8, 0], [27, 0], [30, -40]], "fade_in": 0.05, "fade_out": 1.5},
  "vo": [{"path": "vo/l01.mp3", "at": 1.2}, {"path": "vo/l02.mp3", "at": 6.0, "gain_db": 1}],
  "sfx": [{"type": "impact", "at": 12.0, "strength": 0.6}, {"path": "sfx/whoosh.wav", "at": 11.4, "gain_db": -6}],
  "levels": {"music_db": -5, "vo_db": 0, "sfx_db": -3},
  "duck_db": -11,
  "lufs": -14,
  "true_peak": -1.0,
  "aac_headroom": 1.8
}
```

- **Ducking:** a smoothed VO envelope with a ~0.45 s hold drives the music down by `duck_db` (−8 to −12
  dB works) and back up between lines without pumping.
- **Impacts:** synthesised low hits with a 4 ms attack (no click). Place them 20 ms before the beat
  they belong to.
- **Loudness:** −14 LUFS integrated suits social platforms. AAC encoding raises true peak by roughly
  1.5–2 dB, so the WAV is limited to `true_peak − aac_headroom` (−2.8 dBTP by default) and `deliver`
  re-measures the encoded file. The master should read ≤ −1 dBTP after encoding.
- Stems are written next to the mix (`mix.music.wav`, `mix.vo.wav`, `mix.sfx.wav`) for fixes and for
  Whisper-checking the VO alone.
