# Notes API

Documented read used here: `GET https://api.openstreetmap.org/api/0.6/notes.json`

| Parameter | This skill | Upstream |
|---|---|---|
| `bbox` | Required. `minLon,minLat,maxLon,maxLat`. Each side at most 0.05 degrees. No antimeridian box. | Required. Not larger than the configured area limit (documented as 25 square degrees) and not across the antimeridian. |
| `limit` | 1 to 20, default 10. | 1 to 10000, default 100. |
| `closed` | `--closed-days`, 0 to 7, default 0 (open notes only). | Days since closure. 0 means open notes only. Default 7. -1 means every note. This skill does not send -1. |

The JSON body is a GeoJSON FeatureCollection. Coordinates are WGS84 longitude then latitude. This skill asks only for `application/json`. It does not request the RSS, GPX, XML, or executable JavaScript variants.

Writes exist on the same API and are out of scope: `POST /api/0.6/notes`, `POST /api/0.6/notes/#id/comment`, `POST /api/0.6/notes/#id/close`, and `POST /api/0.6/notes/#id/reopen`. This skill does not call them and does not follow those URLs when they appear in a payload.

A notes search by text (`/api/0.6/notes/search`) and the notes RSS feed are also out of scope.

HTTP 400 means a limit was crossed. HTTP 429 is rate limiting; keep `Retry-After` when the response sends it.
