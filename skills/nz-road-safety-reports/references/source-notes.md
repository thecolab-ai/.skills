# Source notes

Authentication: none

Last verified: 2026-10-08

Verified 8 October 2026. This connector uses the exact catalogue sources
S2096, S2097, S0639, S0638, S0255 and S0218.

## BikeMaps

- `https://bikemaps.org/nearmiss.json?bbox=174.4,-37.2,175.2,-36.4`
- `https://bikemaps.org/collisions.json?bbox=174.4,-37.2,175.2,-36.4`

Live responses are GeoJSON FeatureCollections of WGS84 Points. The Auckland
bbox returned 28 near-miss and 8 collision reports on verification. Properties
include `i_type`, `incident_with`, `date`, `report_date`, `p_type`,
`personal_involvement`, `witness_vehicle`, `injury` and `trip_purpose`.
Only an explicit small set of event/mode fields is exported; narratives, primary
keys, demographics and unspecified future properties are omitted.

`latest_data` is the maximum source event `date` **within the returned bbox**,
not the feed's update time. Source event dates lack timezone offsets; preserve
them without assuming UTC or NZ local time. Retrieval timestamps are UTC.
No explicit data reuse licence was established. Self-reporting is sparse and
biased. Do not rank safety or compare counts without exposure and bias checks.

BikeMaps robots.txt permits these two endpoints. It disallows `/points.json`,
`/incidents.json`, `/hazards.json`, `/thefts.json`, form submissions and other
paths; the connector does not use them.

## NZTA fixed cameras

`https://nzta.govt.nz/travelling-on-our-roads/safety-cameras/about-safety-cameras/fixed-safety-camera-locations`

Published table columns are Suburb, Location, Camera type, GPS coordinates
(Latitude, Longitude), with region headings. A two-row header is supported;
latitude/longitude are converted to GeoJSON longitude/latitude. Trailing commas
in numeric cells are tolerated. Other schema changes fail closed. Source text
`Last update:` becomes `latest_data`, with its stated precision preserved.

Official search-index evidence shows an update of 1 October 2026, but direct
requests returned an Incapsula challenge/403. The synthetic HTML fixture uses
those published columns; it is not a copied NZTA table. No current camera count
or successful direct table retrieval is claimed. NZTA robots.txt excludes search
results, change lists and secure assets; these pages are outside those rules.

## NZTA infringement release: gated

`https://www.nzta.govt.nz/about-us/our-data-and-official-information/official-information-act/proactive-releases`

The official listing states **Safety camera infringement data to 31 May 2026**,
XLSX, 563 KB. The direct listing is blocked from this network and neither the
workbook URL nor workbook schema was verified. Runtime discovery follows only
an XLSX link with that exact release label on the official listing, and only
accepts the declared NZTA hosts. It does not guess asset paths or substitute an
older workbook. On access failure it returns code 4/5. On successful discovery
it returns code 7 with the URL because workbook extraction remains unverified.

Follow-up: retrieve the real workbook on a permitted network, inspect sheets,
headers, time precision and camera identifiers, then add a tested stdlib XLSX
parser using synthetic fixtures of that verified shape. Implement camera/date
filtering and explicit camera-ID spatial joins only after that inspection.
Infringements measure enforcement activity, not near misses or crashes.

## Police RSS

`https://www.police.govt.nz/rss/alerts`

This RSS 2.0 link is exposed by the catalogue traffic-alert page. It is keyless
and structured with `title`, `link`, `description` (escaped HTML) and `pubDate`.
The connector strips description markup without fetching individual alerts.
`latest_data` is the latest publication timestamp in the current RSS items.
The feed is recent national context, not a complete historical archive. It has
no coordinates, so alerts are never presented as spatially matched. District
information is preserved in description text. No open reuse licence established.
Police robots.txt requests a 10-second crawl delay: do not repeatedly poll the
feed more often than that; a CLI invocation performs one request.

## Historical Auckland speed-camera zones

`https://raw.githubusercontent.com/PaulAtKeyboard/OpenCCTV/master/data-speed-cameras-auckland.csv`

This keyless mirror contains 23 historical LGOIMA rows. Verified columns:
`Street`, `Locality (* indicates existing sites)`, `Start of camera zone`,
`End of camera zone`, `Go-live Date`. Coordinates are latitude,longitude strings;
the CLI reverses them to WGS84 and builds straight two-point LineStrings. These
are approximations, not road-centreline geometry or current camera positions.
`latest_data` is the latest stated go-live month (2018-08), not a repository
update date. No explicit data licence established.

Other catalogue near-miss matches are research reports, software, overseas
benchmarks or unrelated datasets, not additional NZ keyless incident feeds.
CAS is already handled by `nzta-crash-data-nz`; this skill does not query CAS.

## Errors and evidence

Exit codes: 2 invalid input, 4 blocked/rate-limited, 5 unavailable, 6 source
schema/parser failure, 7 unsupported operation. JSON errors have provenance,
an empty `results` array and `error`; rate limits preserve `retry_after`.
Corridor runs bounded independent requests concurrently, retains successful
spatial evidence and records each unavailable source explicitly. It never
substitutes the historical CSV for the NZTA fixed-camera table.
