# Sourcing: facts, footage, brand assets and provenance

## Facts

- Every claim on screen or in the VO comes from a source you can link: the organisation's own site or
  report, a public dataset, a published article, a recording the subject shared with you. Keep them in
  `findings.md` as `fact — source URL — date checked`.
- Label anything illustrative (example numbers, mock screens, composite scenes) in `findings.md` and,
  where a viewer could mistake it for fact, on screen.
- Never invent numbers, quotes, customers or results. Round only in the direction of honesty.
- Auto-transcribed quotes and speaker attributions are unverified until a person confirms them. Send
  the list of unverified items with the first preview.
- Reels about real people use only material they have shared or would be comfortable seeing shared back.

## Stock footage and photos

Licence first, then pick.

- **Pexels** (https://www.pexels.com/license/): free for commercial use, attribution appreciated but not
  required. You may not show identifiable people in a bad light or imply they endorse a product, and
  you may not sell the unaltered media. Pexels has a free API (key required) for search; otherwise browse
  the site and download the HD file.
- **Pixabay / Unsplash / Mixkit:** similar permissive licences with their own restrictions (Unsplash is
  photos only; check people/brand rules). Read the current licence page; they change.
- **Manufacturer or brand channels** (product videos, press footage): usually **not** licensed for reuse.
  Many brand terms forbid commercial or promotional reuse without written permission. Use only with that
  permission, credit it, and keep a stock alternative for every such shot.
- **News and social media clips:** do not use without the rights holder's permission.
- **Safety review every clip:** nothing that shows unsafe practice as if it were normal, nothing that
  would embarrass an identifiable person.

## Brand assets

- Use a brand's logo, colours and fonts only for that brand's own video, or with permission. Pull
  colours and type from their published brand guide or site CSS, and logos from their official press or
  brand page.
- Keep logos out of the bottom 15% of phone video (platform UI) and off the final frame unless asked;
  end on the idea.
- Fonts: use typefaces whose licence allows embedding in video (the SIL Open Font License covers most
  Google Fonts). Self-host the files in the project.

## Provenance log

`init` creates `PROVENANCE.md`. Add a row the moment you download anything:

| asset | file | source URL | owner | licence | permission / notes |
|---|---|---|---|---|---|
| aerial coast clip | footage/coast-01.mp4 | https://www.pexels.com/video/... | creator name | Pexels licence | used 00:03–00:07, graded warm |
| music bed | audio/bed.wav | generated, model + seed | you | model licence | prompt in audio/prompt.txt |

Include generated assets (model, seed, prompt) and voices (provider, voice id). Ship the log with the
deliverables so anyone can answer "where did this come from?" months later.

## Privacy

- Client or private material never goes to a public link. Share previews privately.
- Do not commit source recordings, transcripts or personal data into a public repository.
