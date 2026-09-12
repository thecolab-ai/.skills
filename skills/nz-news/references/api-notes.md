# Interview episode discovery

This extends the existing news source skill with programme RSS metadata. It
avoids a duplicate RNZ/news connector. The existing headline/search commands
retain their interfaces; the `interviews` command uses a separate, bounded
transport and explicit result contract.

| Selector | Programme | Source discovery | Observed 2026-09-12 |
|---|---|---|---|
| mike-hosking | The Mike Hosking Breakfast | [Publisher playlist and RSS link](https://omny.fm/shows/the-mike-hosking-breakfast/playlists/podcast) | 93 complete RSS items in the first 512 KiB; 45 title-pattern interview candidates. |
| rnz-morning-report | Morning Report | [RNZ programme](https://www.rnz.co.nz/programmes/morningreport) | robots.txt disallows ChatGPT-User; stop before requesting the feed. |

The publisher playlist links to its public Omny RSS feed. The configured direct
feed URL was resolved from that RSS link, not inferred from an unofficial search
index. Omny documents [feed pagination](https://help.tritondigital.com/user/docs/playlist-feed-sizes),
but this connector deliberately does not traverse pages or assume a public
page-size query parameter. The observed first prefix spanned 2026-08-27 through
2026-09-11 UTC. Counts and coverage will change as new episodes are published.

## Query and temporal contract

`interviews` requires `--programme`; `--limit` accepts 1–100 (default 10).
`--contains` is a case-insensitive title filter. It never searches descriptions,
audio or transcript bodies. All live requests are public GETs.

`query.window=last90days`; `query.as_of` is the actual current UTC instant and
`query.since=as_of-90 days`. Both endpoints are inclusive. Publication timestamps
are parsed from RSS `pubDate` with their explicit timezone, then normalised to
UTC. Missing, invalid or timezone-free dates are excluded and counted. Future
episodes are excluded. RSS publication dates do not establish broadcast dates;
`broadcast_date` stays null. Neither retrieval timestamps nor HTTP Last-Modified
are substituted for source dates.

A title-pattern candidate has a two-to-five-word capitalised prefix before a
colon and an `on` phrase in the rest of its title. Known full-show/panel labels
are excluded. This is intentionally an inspectable discovery heuristic: it can
miss interviews with other titles and can include other named segments. It does
not identify politicians, assess political content or verify a personal identity.

`speaker` preserves that exact title prefix; `speaker_basis` is always
`publisher_title_prefix_unverified`. Its source-title character offsets are
end-exclusive. Source titles remain visible for review; roles in titles are not
normalised into current-office records. This is public-source attribution, not
personal profiling or proof that a particular statement was spoken.

## Transcript and provenance contract

`transcript_availability=advertised` means the feed supplies a valid public HTTPS
`podcast:transcript` URL. It does not mean the URL was requested, access was
permitted, the transcript was human-created, or its words were verified.
Otherwise availability is `unknown`, not unavailable. Transcript URLs, type and
language are retained; no transcript/audio/description content is returned or
stored. Review rights and access restrictions before any separate retrieval.

Each row includes the feed URL, discovery page, retrieval time, response hash,
hash scope, parser version, item ordinal, GUID, exact raw pubDate, field locators
and title-prefix offsets. For a capped read, the SHA-256 covers exactly the
512 KiB prefix supplied to the parser, excluding the extra byte used to detect
truncation. A prefix hash must not be represented as a full-feed hash. No raw
feed bundles are saved by this command.

## Access and failure contract

The transport makes at most two requests (robots.txt, then feed), with ten-second
socket timeouts, no retries, redirects, cookies or environment proxies. It
identifies as ChatGPT-User, checks that agent's robots rules and applicable crawl
delay/rate, and stops for explicit `ai-input=no` or `search=no` content signals.
The signal check is conservative across groups; do not evade a refusal.
Crawl delays above ten seconds stop the bounded probe. Missing robots files
(404/410) are recorded; other robots failures stop discovery.

Only www.omnycontent.com and www.rnz.co.nz are requested. Omny programme URLs are
source references and transcript links are output-only. podcastindex.org is the
XML namespace, not a requested API. Extra catalogue domains cover these public
references for static contract auditing; the actual request allowlist is smaller.

`source_ledger` records HTTP status, transport state and robots decisions. A
bounded feed prefix is `partial`; `coverage.feed_complete` is false. Only closed
RSS item elements are parsed. Malformed XML in the scanned bytes is a schema
failure. An incomplete trailing item is ignored only when the read reached its
explicit cap. A prefix without any complete items is unavailable.

Result states and exit codes: successful candidates `ok` (0), no matching
candidates within the scanned prefix `empty` (0), access refusal `blocked` (4),
upstream/redirect/read failure `unavailable` (5), source parser/schema failure
`schema_error` (6), invalid CLI arguments (2). Failures never become empty success.
Socket timeouts are per blocking operation; smoke adds a 35-second process bound.

Coverage excludes RNZ content while blocked, TVNZ Q+A, Newshub archives, The
Platform, video interviews, other Newstalk programmes and the unscanned RSS tail.
No political persuasion, voter-level inference or full copyrighted transcript
redistribution is implemented.
