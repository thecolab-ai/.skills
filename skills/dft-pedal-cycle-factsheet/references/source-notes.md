# Source notes

- Primary owner: Department for Transport
- Primary source URL: https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-vulnerable-road-user-factsheets/reported-road-casualties-great-britain-pedal-cycle-factsheet-2025
- Data licence: Open Government Licence v3.0 except where otherwise stated
- Licence reference: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- Declared outbound hosts: www.gov.uk, assets.publishing.service.gov.uk
- Access mode: public-download
- Authentication: none
- Last verified: 2026-10-11

The publication page states: "This publication is licensed under the terms of
the Open Government Licence v3.0 except where otherwise stated." Attribute the
Department for Transport. The skill stops when that sentence is absent. The
National Archives page is the licence text; it is not a runtime host.

## Resolution

`tables` requests the pedal-cycle factsheet page on www.gov.uk with a 15 second
timeout and a 2 MB cap. It follows at most three redirects, and only when the
next URL is HTTPS on www.gov.uk or assets.publishing.service.gov.uk with no
query string and no non-default port.

The HTML publication does not itself embed the workbook. It links to the parent
national statistics release,
`/government/statistics/reported-road-casualties-great-britain-vulnerable-road-user-factsheets`.
When the factsheet page has no pedal-cycle ODS link, the command requests that
one parent page and selects the anchor whose text or filename identifies the
pedal-cycle data tables. A stored media hash is not a fallback. Sibling ODS
links (pedestrian, e-scooter, motorcycle) are not requested.

The selected file must be one HTTPS ODS on an allowed host. The zip is read in
memory. Member names, encryption, declared size, compression ratio, and XML
declarations are bounded before worksheet values are accepted. Trailing empty
row and column repeats, including the spreadsheet's unused million-row grid,
are not expanded.

## Table semantics

Worksheet titles and preamble stay with the sheet. Units in a sheet title are
the phrases inside round brackets, such as `pedal cycle billion vehicle miles`
or `Index 2004=100`. Column units are the trailing round-bracket phrase on a
header, such as `%` on `Pedal cyclists (%)`. Square brackets are note markers,
not units.

`office:value` is kept as the source decimal. Display text is separate, so a
value of `2.59` can display as `3`, and `3206` can display as `3,206`.
Percentages stored as text stay text. A blank cell is omitted and is not zero.
The cover sheet says `[x]` means no data when more than one reason applies, and
a blank is used when there is one reason. Filters described in the preamble are
a spreadsheet view; stored cells are still read.

`meta.latest_data` is the table-of-contents field "Date this data was first
published" when every content row gives the same string. It is not the casualty
year and not the retrieval time. `next_publication` is kept on the result when
that column is also uniform. STATS19 is the source named in the workbook.

## Errors

| Code | Type | When |
|---:|---|---|
| 2 | invalid_input | Unknown argument, bad `--limit`, bad `--sheet`, or missing fixture |
| 4 | blocked | HTTP 403, 406, 429, or 451, or a short challenge page. HTTP 429 keeps `Retry-After` |
| 5 | upstream_unavailable | Timeout, connection failure, HTTP 5xx, or too many on-host redirects |
| 6 | schema_failure | Missing licence sentence, missing or ambiguous pedal-cycle ODS link, or a workbook that is not the expected ODS |
| 7 | unsupported_operation | Off-host redirect, query string, byte cap, zip bomb, or an expanded repeat |

Empty numeric output is a schema failure, not a successful empty list. An
upstream failure is not reported as health `pass`.

## Fixture

`tests/fixtures/pedal-cycle-sample.ods` is a small Open Government Licence
excerpt: the publication title, the unit and `[x]` rules, and a two-row
`Table_1` sample including killed `134` and traffic `2.59` displayed as `3`.
`tests/fixtures/not-a-spreadsheet.bin` is synthetic.
