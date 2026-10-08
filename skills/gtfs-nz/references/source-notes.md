# Sources and parser boundaries

Authentication: none

Last verified: 2026-10-08

Verified with real keyless GET downloads on 8 October 2026:

| Feed | Publisher | ZIP | Reuse |
|---|---|---|---|
| `at` | Auckland Transport | https://gtfs.at.govt.nz/gtfs.zip | CC BY 4.0 |
| `metlink` | Greater Wellington Regional Council | https://static.opendata.metlink.org.nz/v1/gtfs/full.zip | Metlink GTFS Terms of Use |
| `busit` | Waikato Regional Council | https://wrcscheduledata.blob.core.windows.net/wrcgtfs/busit-nz-public.zip | No feed-specific licence verified; `licence: null` |
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
  links the GTFS download and states CC BY 4.0. The download redirects to the
  equivalent `orc.govt.nz` host, which is included in the declared allowlist.
- [GTFS schedule reference](https://gtfs.org/documentation/schedule/reference/)
  defines calendar exceptions, service dates, hours above 24 and numeric shape sequences.

Only this verified registry is offered; no arbitrary URL downloads or key-based APIs.
No Metlink skill exists in the lane's starting checkout. Existing `at-transport`
uses AT API endpoints and a subscription key; it is complementary to this ZIP reader.
Metro's developer portal was discovered but a current keyless ZIP was not confirmed,
so Metro is not claimed in the registry.

## Cache and memory

Fresh downloads are streamed to unique temporary files in the chosen cache directory,
validated as GTFS, and atomically replaced. A sidecar stores original UTC retrieval time
and source URL. Stale or invalid cache entries trigger a download; stale files are never
returned as a successful refresh. `feeds` makes a live GET even when cache files exist.
The default maximum age is 24 h, configurable in seconds. ZIPs are never extracted.

CSV uses UTF-8 with optional BOM and Python's CSV quoting parser. Required headers,
non-empty core tables, row widths, table names and sizes are checked. This is a reader,
not a full GTFS validator; it does not validate every unused column or foreign key.
A 10 s urllib timeout bounds network operations, not the entire command duration.
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
