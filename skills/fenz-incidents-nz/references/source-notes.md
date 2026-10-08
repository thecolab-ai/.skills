# Source notes

- Primary owner: Fire and Emergency New Zealand incident reports
- Primary source: https://www.fireandemergency.nz/incidents-and-news/incident-reports/
- Annual data: https://www.fireandemergency.nz/about-us/proactive-releases-oia-responses-and-data-sharing/
- Metadata: https://www.fireandemergency.nz/assets/Documents/About-FENZ/Incident-data/FENZ-Incident-Metadata-2025_12.pdf
- Declared outbound hosts: www.fireandemergency.nz
- Access mode: bounded first-party portal/index retrieval
- Authentication: none
- Last verified: 2026-10-08; verified live by Hawk from omarchy (meaningful live smoke assertions);
  this fix lane still receives Incapsula challenges on the same date.
- Update cadence: operational feed and annual publication dependent
- Website licence: CC BY-NC-ND 4.0, unless otherwise stated:
  https://www.fireandemergency.nz/about-this-website/copyright/

## Operational request repair (8 October 2026)

The old CLI requested `/incidents/` without parameters. The official incident index links each
weekday and region separately: `incidents/?day=Wednesday&region=1`, where North=1, Central=2,
South=3. The corrected CLI supplies these published parameters. No extra authentication or
special headers are required by the published flow. It requests yesterday in NZ by default;
`--day` and `--report-region` let callers choose another published slice.

Hawk verified direct live commands on 2026-10-08 from omarchy, including the blank Location
records F4557313 (Monday) and F4555835 (Saturday). The repaired parser retains empty optional
fields and reports `incomplete_fields`; incident number and date/time remain required. Region
requests are atomic: any access, network or parser failure fails the whole selected operation.
Choosing today's NZ weekday returns today's partial feed, not the same weekday last week.

This fix lane's direct curl/CLI still receives challenge HTML (HTTP 200/403); that network block
is reported separately from source health. The existing two-record visible-text fixture and
`blocked-live.html` retain original capture evidence. New blank-field regression data is clearly
synthetic; no new restricted source captures are bundled.
HTTP 400 and other permanent client errors remain hard smoke failures (exit 6), so the previous
missing-parameter failure can no longer be silently counted as an upstream outage skip.

The parser accepts visible labelled cells in definition-list and table layouts, requires incident
number and date/time, retains Attending Stations/Brigades, and refuses challenge/empty pages.
The source says
the operational extract is incomplete and unsuitable for statistical analysis. Neither the
single-day result nor a failed request proves that no incident occurred.

## Feasibility decision

The connector parses FENZ's labelled operational incident table and marks classifications as
preliminary. The proactive-release page publishes financial-year incident downloads, discovered
at runtime. Its metadata states that each file is one tab-delimited table with one record per
exposure, updated annually. `annual` and `trend` discover these official links and aggregate by the
published Regional Council and Incident Type fields, retaining exposure and distinct-incident counts.

## Parser and maintenance

The deterministic fixtures cover labelled operational fields, official annual resource discovery,
tab-delimited annual rows, regional aggregation, exposure-versus-incident semantics and bounds.
ZIP-wrapped and direct text tables are supported. Missing required annual columns fail closed.

Source-owner expectations: bounded, read-only access; no accounts, submission, notification, booking, payment, mutation, private-data enrichment, or automated contact flows.
