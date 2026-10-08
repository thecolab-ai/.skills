# Source formats and limits

Authentication: none

Last verified: 2026-10-08

Verified directly on 8 October 2026, without authentication. The source registry
was selected using the nz-data-catalogue searches `port`, `vessel`, and `truck turn`.
All four implemented public surfaces returned HTTP 200. No captured datasets are
bundled: parser fixtures contain entirely made-up values in the observed shapes.

## Auckland arrivals (S0540)

Endpoint: https://poal.co.nz/operations/schedules/arrivals/download

The download is UTF-8 CSV, with 13 columns: Vessel, Agent, Wharf, Vessel Ref,
Lloyd's No, Voyage In, Voyage Out, Receivals start, Receivals stop, Arrival,
Departs, Previous Port, Next Port. Arrival and departure timestamps use
`8 Oct 2026 17:30`; the CLI interprets these as Pacific/Auckland local time,
including daylight saving, and emits ISO 8601 with the applicable offset.
Receival strings are preserved because they may say `Refer to Line` or be blank.
IMO and voyage identifiers remain strings. Blank schedule dates become null;
unrecognised dates or changed headers fail with code 6.

There were 156 expected-arrival rows during verification. Keep repeated vessel
names and refs: calls can include berth shifts. The feed can change at any time;
there is no stated update timestamp or exposed historical-query interface.
`latest_data` is therefore omitted. Forecast dates are not a freshness claim.

## Auckland truck times (S0541; related S0534)

Page: https://www.poal.co.nz/customer-centre/truck-turn-times

Read only the server-rendered `truck-turnaround--request-time` and
`truck-turnaround--item--detail` divs. The live block says, for example, `At HH:MM
Truck Turnaround for LOCATION for the last 30 min is N min N sec`. Convert duration
to `turn_seconds`, retaining location, rolling window and request timestamp.
The date in `request_time` supplies the observation date; if its HH:MM precedes
the request across midnight, use the previous calendar day. This date association
is a parser interpretation, not a separately published full observation datetime.
`latest_data` is the newest resulting observation timestamp, at minute precision.

Two facilities were exposed: Fergusson Park and Empty Yard. The page's editorial
"Last updated" date is unrelated to live metric freshness and is ignored. Source
snapshots may lag retrieval. Neither historical observations nor truck volumes
are exposed. Time filters cannot recover past records from the page or cache.

## Tauranga arrivals (S1371)

Page: https://www.port-tauranga.co.nz/operations/shipping-schedules/

The public HTML has In Port, Expected Arrivals and Departed Vessels tables; this
CLI returns only Expected Arrivals, identified by `pot-data-table-2`. Its nine
headers are Vessel Name, IMO, Arrives, Departs, Berth, Agent, Cargo, Last Port,
Next Port. Schedule dates use `DD/MM/YYYY HH:MM` in assumed NZ local time.
`latest_data` is the Expected Arrivals heading's stated update timestamp,
interpreted as Pacific/Auckland. The page says schedules are updated hourly.
There were 102 expected rows during verification; some rows had old ETAs, so
"expected" alone is not a guarantee that a row is upcoming. Apply date filters
and check the primary source before planning operations. Browser CSV export
is unnecessary; no export buttons or scripts are executed.

## Tauranga road queue (S1370)

Page: https://www.port-tauranga.co.nz/truck-turn-time/

Parse the `Truck Turn Data - Last 60 Minutes` heading and `Current road queue is:
N trucks` text. `latest_data` is the heading's stated snapshot time in NZ local
time. Three trucks were displayed during verification. This page describes
turn-time targets and shows cameras but does not expose a numeric turn-time series.
The CLI returns `metric: road_queue`, `queue_trucks` and `window_minutes`; do not
convert this count into a duration or fetch camera images.

## Other catalogue sources and access policy

`sources` also lists Tauranga annual DOCX trade tables (S1372), Ministry of Transport
FIGS container/productivity dashboards (S0535/S1374) and Stats NZ cargo imports
via Figure.NZ (S1375). These are discovery links, not runtime fetches. No claims of
live health are made for them. Annual/quarterly freight statistics need separate
parsers; FIGS' catalogue note warns that Auckland data are absent from 2025 Q3.
`sources` retrieval times describe reading this bundled registry, not those feeds.

Auckland robots.txt disallows administration, search and login routes, but permits
the two implemented public paths. Both poal.co.nz and www.poal.co.nz are checked
independently by the CLI. Tauranga robots.txt disallows wp-admin except admin-ajax
and a security path; the two implemented pages are permitted. The linked Tauranga
[disclaimer](https://www.port-tauranga.co.nz/disclaimer/) describes security
monitoring. No reuse licence was stated on the verified feeds; omit `licence`
rather than assigning the skill's MIT code licence to port data. Review current
terms before publishing substantial extracts, and attribute the publisher.

HTTP uses the repository nzfetch helper with a 10-second timeout per attempt,
redirect host restrictions and a 4 MB limit. Configured helper retries may lengthen
an entire command; smoke probes bound each subprocess at 45 seconds. No browser,
login, protected API or automatic repeated polling is used.

## Errors and cache

JSON failures have `meta`, empty `results`, and `error` with numeric code and type:
2 invalid_input; 4 blocked/rate-limited (preserving Retry-After);
5 upstream_unavailable; 6 schema_failure. A failed request is never presented as
an empty successful dataset. Errors carry attempt time; cached successes retain
their actual retrieval time. Corrupt/expired caches are refreshed and no stale
fallback is used. Read-only filesystems disable cache writes without disabling
retrieval. Cache files are implementation detail and must never be committed.
