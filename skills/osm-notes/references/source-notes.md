# Source notes

- Primary owner: OpenStreetMap contributors
- Primary source: https://api.openstreetmap.org/api/0.6/notes.json
- Operator: OpenStreetMap Foundation, api.openstreetmap.org
- Public note page host: www.openstreetmap.org
- Data licence: Open Database License (ODbL) 1.0
- Licence URL: https://opendatacommons.org/licenses/odbl/1-0/
- Attribution: © OpenStreetMap contributors
- Authentication: none
- Last verified: 2026-10-11

## Licence evidence

On 2026-10-11 the copyright page https://www.openstreetmap.org/copyright returned HTTP 200 and stated: "OpenStreetMap is open data, licensed under the Open Data Commons Open Database License (ODbL) by the OpenStreetMap Foundation (OSMF)."

The API 0.6 notes documentation shows the same terms on the XML notes response: copyright "OpenStreetMap and contributors", attribution "https://www.openstreetmap.org/copyright", and license "https://opendatacommons.org/licenses/odbl/1-0/". The JSON notes document does not repeat that licence object. This skill still reports the licence because the copyright page and the documented XML response state it. The code licence of this skill is not the data licence.

If a later copyright-page read does not still state the Open Database License, treat the licence as unknown and do not describe the data as reusable.

## What this command reads

`notes` performs one HTTPS GET of `/api/0.6/notes.json` with `bbox`, `limit`, and `closed`. The upstream box is `left,bottom,right,top`. A note is returned when its point lies in that box. Results are in the API order: most recently changed first.

`latest_data` is the newest source timestamp among the returned notes' `date_created`, `date_closed`, and comment dates. Those timestamps stay in the source form `YYYY-MM-DD HH:MM:SS UTC`. It is not the retrieval time. An empty result omits `latest_data`.

`retrieved_at` is when this command received the response. For `--fixture`, it is the parse time of the local file, and `source_url` stays the collection URL because no live request was made.

## Bounds

- One GET per invocation, one thread, timeout 15 seconds.
- `--limit` 1 to 20. The upstream maximum is much higher; this skill does not use it.
- Each bbox side is at most 0.05 degrees. The upstream area limit is larger; this skill does not use it.
- Response bodies above 262144 bytes fail as upstream unavailable.
- `--closed-days` 0 returns open notes only. 1 to 7 is passed as the upstream `closed` day count. `closed=-1` (every closed note) is rejected.
- Redirects are accepted only when they stay on https://api.openstreetmap.org/api/0.6/notes.json.
- The User-Agent is `thecolab-osm-notes/1.0 (+https://github.com/thecolab-ai/.skills; read-only)`.

The OSMF API usage policy says the editing API is not a bulk read service and asks for an identifying User-Agent, at most two download threads, and no automated website-form submission. This command is the documented notes bbox read, not a map-data download and not a write. It does not call planet.osm, Overpass, Nominatim, or Photon. Do not loop it.

## Omitted account fields

Upstream comments can include `uid`, `user`, `user_url`, and HTML. Upstream note properties can include `comment_url`, `close_url`, and `reopen_url`. Those fields are not copied into the result. The result keeps note id, status, WGS84 coordinates, source timestamps, comment action, comment text, and a public note page URL on www.openstreetmap.org. Comment text is capped at 2000 characters and marked `text_truncated` when cut. Comment text can still name a person; that text is the note, not an account field added by this skill.

## Errors

Exit 2 invalid input, 4 blocked or rate limited (Retry-After is preserved), 5 upstream unavailable or timeout, 6 schema mismatch, 7 refused redirect or any non-read request. HTTP 400 from a crossed upstream limit is invalid input. Empty `features` is a successful empty result, not an outage. With `--json` or `--format geojson`, the error envelope goes to stdout and the process exits with `error.code`.

## Coverage

`osm-nz` reads Overpass map objects. It does not read this notes collection. This skill does not replace it.
