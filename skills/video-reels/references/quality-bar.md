# Quality bar

The target is a lyric-video-grade piece where every line has its own visual idea and every cut lands on
the audio. These rules come from shipped reels and the feedback on them.

## Story and pacing

1. **One idea per line, one visual metaphor per idea.** If a line is "we shipped 40 features", the frame
   is not the number 40; it is something that *shows* forty (a stack building, a counter spinning out).
2. **Long holds.** The most common feedback on fast reels is "too fast to read". Hold each line long
   enough to read twice. When in doubt, cut words, not hold time.
3. **Contrast.** Dense set pieces, then near-empty frames before the drops. Silence and black are tools.
4. **Build around the audience.** Their in-jokes, their vocabulary, their problems, mined from real
   sources they would recognise. Generic hype reads as generic.
5. **End on an image or idea, not a logo slate.** Keep a tiny sign-off; the last thing people see should
   be the thought you want them to keep.
6. **Plan two rounds.** A rough pass reviewed as stills or a low-res preview, then a polish pass.

## Look

7. **One accent colour plus near-black.** Off-white for type, a few greys for texture, one accent for
   emphasis. Add a subtle vignette and film grain. Ban everything else.
8. **Reuse a small set of motifs** (corner marks, one bracket style, one transition) so the piece feels
   designed rather than assembled.
9. **Texture layers:** micro labels, callout leader lines, corner marks, typing cursors, readouts in tiny
   mono. Keep them below the reading layer in contrast.
10. **Depth where it earns it:** a few WebGL hero scenes (terrain, tunnels, particle-formed type) with a
    moving camera; 2D canvas for type-heavy scenes. See `render-and-qa.md` for the WebGL fixes.

## Type

11. **Three typefaces with fixed jobs:** an impact grotesk (condensed, heavy), a monospace "machine
    voice" (prompts, labels, data), and a serif for the emotional lines. Do not swap jobs.
12. **Type as the hero:** slams, scramble-locks, split letters, text on paths, odometer counters, a
    typing cursor. Use one or two per scene, not all at once.
13. **Phone sizes:** body ≥ 64 px at 1080×1920; headlines fill the safe width; nothing important in the
    top ~220 px or bottom ~300 px (platform UI), and no logos in the bottom 15%.

## Timing

14. **Every cut, word and hit lands on the audio.** Cuts on bars, hits on beats, on-screen words on the
    VO word timestamps from `whisper` or `voice`. Never time by eye from a waveform.
15. **Choose the audio form per brief:** VO + score, instrumental only, or a sung track. Not every video
    is a song.
16. **Flashes ease in.** An accent flash should ramp over ~3 frames and *peak* on the beat. A 1-frame
    hard onset reads as a glitch (and the flicker detector will flag it).
17. **30 fps by default.** 60 fps doubles render time and is rarely visible in type-led work.

## Voice

18. **Whisper-check every VO line.** If a word is misheard, respell it or rewrite the line; drop a line
    rather than ship a mangled name.
19. **Pace:** about 2.3–2.8 words per second reads well with on-screen text. Over 3 words/s feels rushed.

## Honesty

20. **Facts from real sources only.** Label anything illustrative. Send the list of unverified items
    (auto-transcribed quotes, speaker attributions, estimates) with the first preview.
21. **Affectionate, never embarrassing.** For reels about people or groups, leave out anything that would
    genuinely embarrass someone if it were shared back to them, and flag anything borderline.
