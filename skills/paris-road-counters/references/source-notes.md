# Source notes

- Primary source: https://opendata.paris.fr/explore/dataset/comptages-routiers-permanents/information/
- Authentication: none
- Last verified: 2026-10-11

Verified 2026-10-11 against `opendata.paris.fr` only. Requests use a 15 second
timeout, a named User-Agent, and refuse redirects that leave that host.

## Dataset

- Catalogue: `comptages-routiers-permanents`
- Title: Comptage routier - Données trafic issues des capteurs permanents
- Publisher: Direction de la Voirie et des Déplacements - Ville de Paris
- Producer, from the dataset description: Service des Déplacements - Poste Central d'Exploitation Lutèce
- Landing page: https://opendata.paris.fr/explore/dataset/comptages-routiers-permanents/information/
- Metadata: `/api/explore/v2.1/catalog/datasets/comptages-routiers-permanents`
- Records: the same dataset's `/records` endpoint, Explore API v2.1
- Licence name stated by the catalogue: Open Database License (ODbL)
- Licence URL stated by the catalogue: http://opendatacommons.org/licenses/odbl/
- Timezone stated by the catalogue: `Europe/Paris`
- DCAT granularity: `Horaire`
- The description says the feed is a rolling 13 months published the next day (J-1)
- `data_processed` is the catalogue processing time and is copied to `latest_data`. It is not the newest `t_1h`
- `records_count` is the number of arc-hour rows in the catalogue (tens of millions on 2026-10-11). It is not a vehicle total. `counts` never pages that catalogue; `--limit` is 1 to 20

The skill code is MIT. That licence does not cover the records. ODbL
attribution is the publisher above, the dataset title, and the licence URL.
Share-alike applies when someone makes a database from the records. Fixtures
under `tests/fixtures/` are synthetic and are not an extract.

`counts` reads the catalogue document first and refuses the records when the
live licence name or licence URL is not this ODbL statement. A missing licence
is a schema failure. A different licence is an unsupported operation. Neither
is returned as an empty success.

## Not this dataset

Do not call these from this skill:

- The historical series and the geographic referential are separate datasets. The 2019 notice points at them on another host. This skill's allowlist is only `opendata.paris.fr`
- Belib charging availability is not a road counter
- `nz-traffic-counts` is New Zealand councils and NZTA, not Paris

The 2019 notice attachment is documentation, not a row download. The CLI does
not fetch it. Its field definitions are the semantics below. Notice title:
NOTICE données trafic capteurs permanents, 7 juin 2019, Ville de Paris,
Direction de la Voirie et des Déplacements.

## Counter semantics

The notice's traffic file is one row per `iu_ac` and `t_1h`. `iu_ac` is the
traffic-arc identifier. Direction is `libelle_nd_amont` toward
`libelle_nd_aval`. The opposite direction is a different arc. Nearby arcs
repeat flow because count stations sit between major junctions and flow is
generally conserved along a section. Do not add arcs together and call the
result a screenline or a network total.

`t_1h` is a timestamp without a zone in the notice, meaning Paris civil time,
at the end of the elaboration hour. The notice's example `2019-01-01 01:00:00`
is the hour from 00:00 to 01:00. A stamp of `00:00:00` is the last hour of the
previous civil date. The API is asked for `timezone=Europe/Paris` and the
offset on `t_1h` must match that zone. A naive stamp, or a UTC offset, is a
schema failure rather than a relabelled hour. `derived_period_start` subtracts
60 minutes from the published stamp. `date_debut` and `date_fin` are reference
availability dates for the arc, not the count hour. An earlier `date_fin` is
preserved and flagged; it does not replace `t_1h`.

`q` is a real number: vehicles counted at the loop during that hour, in that
direction. It is all vehicles the loop counted. There is no car, goods, cycle,
or pedestrian split in this dataset. Some stations measure occupancy only, so
`q` is null while `k` is present. Null is unobserved, not zero. The notice and
catalogue state no small-count suppression rule. A negative `q` is preserved
and warned, not coerced to zero.

`k` is a real number: percent of the hour the loop was occupied. The notice's
example is 25 percent, meaning vehicles were present for 15 minutes. Do not
add `k` to `q`. The same `q` can be fluid at night or saturated at the peak.
The published bands, with the lower edge in the upper band, are:

| k | etat_trafic label |
|---|---|
| 0% ≤ k < 15% | Fluide |
| 15% ≤ k < 30% | Pré-saturé |
| 30% ≤ k < 50% | Saturé |
| 50% ≤ k | Bloqué |

The notice stores `etat_trafic` as an integer 0 Inconnu, 1 Fluide, 2
Pré-saturé, 3 Saturé, 4 Bloqué. The Explore records API returns the French
label, not the integer. Labels confirmed on 2026-10-11: Inconnu, Fluide,
Pré-saturé, Saturé, Bloqué. This skill keeps the label it received. When `k`
falls outside the band for that label, both values are kept and a warning is
added. `Inconnu` is not replaced with a band computed from `k`.

`etat_barre` in the notice is 0 Inconnu, 1 Ouvert, 2 Barré, 3 Invalide. The
API again returns labels. Ouvert, Barré, and Invalide were present on
2026-10-11. A query for the label Inconnu matched zero rows that day; the
notice code is still accepted as a filter and an empty result stays empty.
Anything other than Ouvert is not an open-road count.

## Geometry

API `geo_point_2d` is WGS84 `lon` and `lat`. API `geo_shape` is a GeoJSON
Feature whose coordinates are longitude then latitude. `--bbox` is converted
to Explore `in_bbox(geo_point_2d, south, west, north, east)`, which is point
containment, not intersection with the line. The 2019 notice's separate
referential file is EPSG:2154. This command does not read or reproject that
file. Rows without geometry are still counts.

## Errors

| Condition | Code | Type |
|---|---:|---|
| Bad limit, arc, hour, window, or bbox | 2 | invalid_input |
| HTTP 429, with Retry-After preserved | 4 | blocked |
| HTTP 401, 403, or 451 | 4 | blocked |
| Timeout, HTTP 404, 408, 500, 502, 503, 504 | 5 | upstream_unavailable |
| Malformed, truncated, or inconsistent JSON; naive or non-Paris `t_1h`; missing licence | 6 | schema_failure |
| Off-host redirect, or a live licence that is not confirmed ODbL | 7 | unsupported_operation |

An empty `results` array with `total_count` 0 is a successful empty match.
Outage and licence refusal are not empty successes.
