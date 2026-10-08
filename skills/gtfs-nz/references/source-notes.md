# Sources and parser boundaries

Authentication: none

Last verified: 2026-10-08

Verified with real keyless GET downloads on 8 October 2026:

| Feed | Publisher | ZIP | Reuse |
|---|---|---|---|
| `at` | Auckland Transport | https://gtfs.at.govt.nz/gtfs.zip | CC BY 4.0 |
| `metlink` | Greater Wellington Regional Council | https://static.opendata.metlink.org.nz/v1/gtfs/full.zip | Metlink GTFS Terms of Use |
| `busit` | Waikato Regional Council | https://wrcscheduledata.blob.core.windows.net/wrcgtfs/busit-nz-public.zip | No feed-specific licence verified; `licence` omitted |
| `orbus` | Otago Regional Council | https://www.orc.govt.nz/transit/google_transit.zip | CC BY 4.0 |

Official discovery/licence pages:

- [AT static GTFS](https://at.govt.nz/about-us/at-data-sources/general-transit-feed-specification)
  links the ZIP and states CC BY 4.0.
- [Metlink GTFS download and Terms of Use](https://www.metlink.org.nz/legal/general-transit-feed-specification)
  links the static ZIP, disclaims schedule accuracy and allows feed changes/discontinuation.
  Do not infer a Creative Commons licence from Greater Wellington's general GIS portal.
- [BUSIT Transit app](https://www.busit.co.nz/using-the-bus/transit-app/)
  links the public blob ZIP under “View the GTFS feed”. This feed has no feed_info table.
- [Otago privacy and terms](https://www.orc.govt.nz/privacy-and-tscs)
  links the GTFS download and states CC BY 4.0. The download returns a 307 to a relative versioned path under `/media/` on
  the same `www.orc.govt.nz` host. Redirects must remain HTTPS on declared hosts.
- [GTFS schedule reference](https://gtfs.org/documentation/schedule/reference/)
  defines calendar exceptions, service dates, hours above 24 and numeric shape sequences.

Only this verified registry is offered; no arbitrary URL downloads or key-based APIs.
No Metlink skill exists in the lane's starting checkout. Existing `at-transport`
uses AT API endpoints and a subscription key; it is complementary to this ZIP reader.
Metro's developer portal was discovered but a current keyless ZIP was not confirmed,
so Metro is not claimed in the registry.

## Cache and memory

Fresh downloads are streamed to unique temporary files in the chosen cache directory,
validated as GTFS, and atomically replaced. A sidecar stores original UTC retrieval time, source URL, ZIP size and SHA-256.
Cache reads verify that identity against the opened ZIP, preventing concurrent
replacements or interrupted writes from attaching unrelated provenance. Stale or invalid cache entries trigger a download; stale files are never
returned as a successful refresh. `feeds` reuses fresh cache files unless `--refresh` is given and reports `cached`
on each available record.
The default maximum age is 24 h, configurable in seconds. ZIPs are never extracted.
The cache lives at `$XDG_CACHE_HOME/thecolab-gtfs-nz`, falling back to
`~/.cache/thecolab-gtfs-nz`; `GTFS_NZ_CACHE_DIR` or `--cache-dir` overrides it.
Installed skill directories need no write access.

CSV uses UTF-8 with optional BOM and Python's CSV quoting parser. Required headers,
non-empty core tables, row widths, table names and sizes are checked. This is a reader,
not a full GTFS validator; it does not validate every unused column or foreign key.
A 10 s socket timeout and monotonic 50 s deadline bound each ZIP download.
Network read failures are upstream errors (5); cache write failures are schema/cache
errors (6). HTTPS redirects outside the declared host allowlist fail with code 7.
Repeated stop-time/shape queries scan those tables again; they do not create a large
all-feed in-memory index. Stops/routes are small; departures retain active trip metadata
and at most the output limit, and shapes retain geometry only for the requested route.

Calendar exceptions override weekday service. Calendar-dates-only feeds are supported.
All verified agencies use Pacific/Auckland. Other timezones fail explicitly.
Departure times use GTFS elapsed service-day seconds; preserving them avoids ambiguous
wall-clock/UTC conversions on daylight saving days. Blank departure times are reported
as untimed; arrival times are not silently substituted. All published shape variants
are returned regardless of today's calendar; bbox tests segments as well as vertices.

## Fixtures

`tests/fixtures/at-sample.zip` contains three real active route `101-202` trips,
their complete stop_times, stops and shapes, and unchanged metadata/calendar tables.
`tests/fixtures/source-sample.json` records retrieval provenance and trimmed counts.
The AT data are CC BY 4.0; the selection is the modification. Synthetic edge cases
in the deterministic tests are explicitly derived by modifying those captured tables,
including calendar-only exceptions, overnight times, no-pickup stops and frequencies.

## Output interpretation

`meta.latest_data` is a string containing the source feed_info validity range,
for example `2026-09-30/2027-01-24`; a lone stated boundary is a single ISO date.
It does not assert when the feed was published. Original `feed_start_date`,
`feed_end_date` and `feed_version` remain in `meta.feed_info` records. BUSIT omits
`latest_data` because it publishes no feed_info. Registry envelope provenance uses
string fields for NZ public transport agencies; individual feed records carry
source-specific provenance and optional licence/validity fields.

Mode filters map 0 and 900–999 to tram; 5/6/7 and 1300–1499 to cable;
3/11, 200–299, 700–899 to bus; 1/2/12, 100–199, 300–499 to rail;
4, 1000–1099, 1200–1299 to ferry. Other types map to `other`.

Departure rows with the maximum numeric stop_sequence in their trip carry
`terminates: true`, identifying terminal arrivals; filter those for boarding-only
analysis. Frequency expansion is unsupported only when an active frequency trip
serves an included stop; frequency trips elsewhere add a warning.
