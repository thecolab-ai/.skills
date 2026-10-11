# Source notes

- Primary owner: Direction de la Voirie et des Déplacements - Ville de Paris
- Primary source: https://parisdata.opendatasoft.com/explore/dataset/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel/
- Records endpoint used in JSON `meta.source_url`: https://parisdata.opendatasoft.com/api/explore/v2.1/catalog/datasets/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel/records
- Dataset metadata read on every live command: https://parisdata.opendatasoft.com/api/explore/v2.1/catalog/datasets/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel
- Dataset id: `belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel`
- Dataset title: Belib' - Points de recharge pour véhicules électriques - Disponibilité temps réel
- Data licence: Open Database License (ODbL)
- Licence URL stated by the dataset metadata on 2026-10-11: http://opendatacommons.org/licenses/odbl/
- Attribution: Contains Belib' live charge-point availability from Direction de la Voirie et des Déplacements - Ville de Paris, licensed under the Open Database License (ODbL).
- Declared outbound hosts: parisdata.opendatasoft.com
- Access mode: keyless OpenDataSoft Explore API v2.1 records
- Authentication: none
- Last verified: 2026-10-11

This skill reads Paris Belib live charge-point availability. It is not the New
Zealand EECA public-charger register and it does not select New Zealand rows.
The repository pack `nz-public-data` is the public read-only pack; the geography
of this dataset is Paris.

## What was verified on 2026-10-11

A keyless GET of one record and of the dataset metadata stayed on
`parisdata.opendatasoft.com` with no redirect. Metadata `license` was
`Open Database License (ODbL)` and `publisher` was Direction de la Voirie et
des Déplacements - Ville de Paris. `modified_updates_on_data_change` was true.
The dataset timezone is Europe/Paris. Record `last_updated` values are
timestamps with a numeric offset; the newest point observed was
`2026-10-11T18:12:05+00:00`. The oldest observed point was
`2026-06-08T05:25:57+00:00` with status `Inconnu`. About 1975 points were
present. Status counts at that read were Disponible 1083, Occupé (en charge)
781, En maintenance 58, Inconnu 50, and Mise en service planifiée 3.
`code_insee_commune` was `75056` for 1968 points and null for 7. Do not fill
a null commune code.

The live command refuses the records unless metadata `dataset_id` is this
dataset and `license` is exactly `Open Database License (ODbL)`. A different
licence is not treated as success. The licence URL is copied from metadata
when it is a short string. This skill does not fetch the licence host.

## Request bounds

- One metadata GET, then one records GET. No retry loop and no cache.
- Timeout 15 seconds. Body cap 262144 bytes. Responses are not decompressed
  past that cap.
- `limit` 1 to 20. `order_by` is fixed at `last_updated desc`. There is no
  offset, so this cannot page occupancy history.
- `select` asks only for `id_pdc`, `statut_pdc`, `url_description_pdc`,
  `last_updated`, `arrondissement`, `adresse_station`, `coordonneesxy`, and
  `code_insee_commune`.
- Optional `where` is built only from a validated id (`id_pdc="..."`) and/or
  `in_bbox(coordonneesxy, minLat, minLon, maxLat, maxLon)`. That is point
  containment, applied by the API before the limit. The CLI bbox argument is
  WGS84 `minLon,minLat,maxLon,maxLat`.
- User-Agent: `thecolab-belib-ev-live/1.0 (+https://github.com/thecolab-ai/.skills)`.
- HTTPS only. A redirect to any other host, or to plain HTTP, is rejected
  before it is followed. Proxies are disabled for these requests.
- The static-description URL in each record points at the separate static
  Belib dataset. It is returned as a link and is not requested.

## Fields and freshness

`latest_data` is the original `last_updated` string of the newest record in
the returned page. Because the page is ordered by that field descending, it is
the most recently updated matched point, not the catalogue `modified` time and
not the retrieval time. `update_age_seconds` is derived from retrieval minus
that source timestamp. `meta.current` is true only when that age is between
-15 minutes and 3 hours. `--require-current` turns a false result into an
error and does not invent a fresher row.

Status values are returned as published. Known values include Disponible,
Occupé (en charge), En maintenance, Inconnu, and Mise en service planifiée.
New non-empty status text is kept. Records are not dropped for being occupied,
in maintenance, unknown, or planned.

Coordinates are WGS84 longitude then latitude in `coordonneesxy`. GeoJSON uses
the same order. `--format geojson` emits a FeatureCollection with the same
provenance `meta`.

## Errors

| Condition | Code | Type |
|---|---:|---|
| Malformed limit, id, bbox, or fixture path | 2 | invalid_input |
| HTTP 429, with raw Retry-After when present | 4 | blocked |
| Timeout, other network failure, HTTP 503 and other 5xx | 5 | upstream_unavailable |
| Non-JSON, truncated JSON, unexpected fields, bad coordinates, row cap | 6 | schema_failure |
| Licence is not ODbL, off-host redirect, or `--require-current` fails | 7 | unsupported_operation |

An empty `results` array is a successful empty match. It is not a fabricated
row and it is not a pass of the live freshness check.

## Fixtures

`tests/fixtures/records-positive.json` is one public record retrieved
2026-10-11 from this ODbL dataset (point `FR*V75*E9012*06*3`). The other
fixtures are synthetic parser and HTTP cases. They contain no personal fields.
The positive excerpt is shared here with the attribution above.
