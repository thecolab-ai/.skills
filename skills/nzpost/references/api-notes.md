# NZ Post Tracking API Notes

## Discovery method

Playwright/Chromium was used to navigate to https://www.nzpost.co.nz/tools/tracking, enter tracking
number `00794210392715622565`, and capture all network requests/responses.

## Primary endpoint

```
GET https://tools.nzpost.co.nz/tracking/api/parceltrack/parcels?tracking_reference=<TRACKING_NUMBER>
```

### Headers used by the CLI

```
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) Gecko/20100101 Firefox/151.0
Referer: https://www.nzpost.co.nz/tools/tracking
Content-Type: application/json
```

No authentication token, cookie, or CSRF header is required. Direct curl requests returned 200
without the `Referer` header during review on 2026-05-25. The CLI still sends it for parity with the
NZ Post website, and browser CORS responses advertise `access-control-allow-origin:
https://www.nzpost.co.nz`.

### Response shape

```json
{
  "message_id": "...",
  "success": true,
  "status_code": 1,
  "results": [
    {
      "tracking_reference": "00794210392715622565",
      "tracking_events": [
        {
          "date_time": "2026-03-01T21:54:15Z",
          "description": "The sender has allocated a tracking number to your parcel.",
          "edifact_code": "997",
          "seqref": "8292916417",
          "source": "CME",
          "status": "Tracking number allocated to parcel"
        },
        ...
        {
          "date_time": "2026-03-12T20:34:07Z",
          "depot_name": "Papakura Depot",
          "description": "Your parcel has been delivered...",
          "pbu": "015199",
          "edifact_code": "22",
          "seqref": "8317681627",
          "run_name": "Papakura",
          "source": "CME",
          "status": "Delivered"
        }
      ]
    }
  ]
}
```

### No-data response shape

Unknown or invalid references can still return HTTP 200 with `success: true`. Callers must check
`status_code` and nested result errors, not only the top-level `success` flag.

```json
{
  "message_id": "...",
  "success": true,
  "status_code": 2,
  "results": [
    {
      "tracking_reference": "00000000000000000000",
      "errors": [
        {
          "code": 400002,
          "message": "Invalid parameter(s)",
          "details": "No data found for this Tracking Reference"
        }
      ]
    }
  ]
}
```

### Event object fields

| Field | Type | Notes |
|-------|------|-------|
| `date_time` | ISO 8601 UTC string | Always present |
| `status` | string | Human-readable status label, always present |
| `description` | string | Longer description, always present. May contain HTML links. |
| `edifact_code` | string | Internal status code (e.g. "22" = Delivered, "32" = With courier) |
| `depot_name` | string | Optional, present once parcel is at a depot |
| `run_name` | string | Optional, courier run/area name |
| `pbu` | string | Optional, depot PBU code |
| `source` | string | Always "CME" in observed data |
| `seqref` | string | Sequential event reference ID |

### Notable edifact_codes

| Code | Meaning |
|------|---------|
| 997 | Tracking number allocated |
| 205 | Pickup request received |
| 206 | Allocated to driver |
| 13 | Collected from sender |
| 8 | Processed at depot |
| 58 | Ready for courier |
| 40 | Delayed |
| 32 | With courier for delivery |
| 22 | Delivered |

## Secondary endpoints (also discovered, not used by CLI)

- `GET https://tools.nzpost.co.nz/tracking/api/details?tn=<TRACKING_NUMBER>` - returns photo addon status and related tracking references
- `GET https://tools.nzpost.co.nz/tracking/api/parcelcontrol/<TRACKING_NUMBER>/all?start_date=<DATE>` - returns delivery control options (redirect, ATL, etc.)
- `GET https://tools.nzpost.co.nz/tracking/api/pcv4/tracking-masks` - returns regex patterns for valid tracking number formats

## Tracking number formats (from tracking-masks endpoint)

The API accepts a wide range of formats including:
- Pure digits: 5, 6, 8, 10, 11, 12, 13, 14, 18, 20, 22, 30 digits
- Alphanumeric: various patterns with letter prefixes (JD, RMA, RMC, TP, TPW, etc.)
- International: UPU format (2 letters + 9 digits + 2 letters, e.g. `EA123456789NZ`)

The CLI validates against a simplified subset covering the most common NZ domestic formats.

## Rate limiting / anti-bot

No rate limiting was observed during testing. The endpoint is served via Cloudflare (`cf-ray` header
present). No CSRF token or session cookie is needed.

## Address suggest endpoint

```
GET https://tools.nzpost.co.nz/legacy/api/suggest?q=<QUERY>&max=<LIMIT>
```

The correct limit parameter is `max=N` (an integer). An earlier note incorrectly documented this as
`MaxData=max:N` -- that parameter name was wrong and the colon-in-value theory was a misdiagnosis.
The `Accept: application/json` header must be included or the endpoint returns a "Bad request" error.

```
Headers:
  User-Agent: <Firefox UA>
  Referer: https://www.nzpost.co.nz/tools/address-postcode-finder
  Accept: application/json
```

Response shape: `{"success": true, "addresses": [{"DPID": ..., "FullAddress": "...", ...}], "status": "success"}`

## PostShop locations endpoint

```
GET https://api.nzpost.co.nz/digital/postshop-locations/v2/locations?type=NEARBY&value=<JSON>&max=<N>
GET https://api.nzpost.co.nz/digital/postshop-locations/v2/locations?type=KEYWORD&value=<TEXT>&max=<N>
```

### Real location type strings (verified 2026-05-25)

| CLI flag value | API `type` field |
|----------------|-----------------|
| `postshop` | `PostShop` |
| `postbox` | `Postbox` (also matches `Postbox Lobby` via substring) |
| `parcel-collect` | `Third Party Partner` |
| `all` | (no filter) |

Note: `ParcelCollect` and `PostBox` do NOT appear in live API responses. Earlier documentation was
wrong.

### Hours field

The `hours` field is a **list** of objects, one per day:

```json
[
  {"day": 0, "open": "08:30", "close": "17:30", "closed": false},
  {"day": 5, "open": "09:00", "close": "17:00", "closed": false},
  {"day": 6, "open": null, "close": null, "closed": true}
]
```

`day` uses ISO weekday numbering: 0=Monday, 6=Sunday (matches Python `datetime.weekday()`).
When `closed` is true, `open`/`close` may be null.

### Geocoding via KEYWORD

Use `type=KEYWORD` with a place name to get coordinates from the first matching location:

```
GET .../locations?type=KEYWORD&value=Clevedon&max=1
```

Response locations include `lat` and `lng` fields (float). This is the preferred geocoding path;
OSM Nominatim is the fallback.
