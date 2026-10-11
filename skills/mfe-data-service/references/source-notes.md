# MfE Koordinates catalogue

- Primary owner: Ministry for the Environment
- Primary source: https://data.mfe.govt.nz/services/api/v1/data/
- Data licence: Per layer. Accepted only when the layer document field license.type is cc-by and license.version is a known Creative Commons Attribution version (1.0, 2.0, 2.5, 3.0 or 4.0) or absent. A missing licence, CC0, NonCommercial, NoDerivatives or ShareAlike type is refused. The skill's MIT code licence is not the data licence.
- Declared outbound hosts: data.mfe.govt.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

## What was verified

On 11 October 2026, unauthenticated GETs with a 15-second timeout returned:

- `GET /services/api/v1/data/?q=flood&page_size=1` — HTTP 200, a one-element JSON list. The card included integer `id`, `type` `layer`, `title`, and `published_at`. It did not include `license`.
- `GET /services/api/v1/layers/125035/` — HTTP 200 JSON. `license.type` was `cc-by`, `license.version` was `4.0`, `license.title` was `Creative Commons Attribution 4.0 International`. `data.feature_count` was an integer. `data.fields` was JSON null (a grid layer, not an attribute table).
- `GET /services/api/v1/layers/117733/` — HTTP 200 JSON for a vector layer. `license.type` was `cc-by`, `license.version` was `4.0`, `data.feature_count` was a positive integer, and `data.fields` was a list of objects with string `name` and `type`. The first field name was `Shape`.
- `GET /services/api/v1/data/?q=__no_such_mfe_layer_zzqq__&page_size=1` — HTTP 200 body `[]`.
- `GET /services/query/` — HTTP 404 `Not found`. This skill does not call a query path. A keyed query service is out of scope even where a deployment answers 403.

Search cards mix `layer`, `table` and `document` types. `layer` reads only `/layers/{id}/`. A table id is not treated as a layer.

## Behaviour

- Timeout 15 seconds. Response cap 512 KiB. Search limit 1–20, sent as `page_size`, and also applied locally if the payload is longer.
- Redirects must stay on `data.mfe.govt.nz`. Any other host is an error.
- `published_at` is the Koordinates publication timestamp copied through unchanged. It is not a monitoring period and not the year embedded in a title.
- `feature_count` is the integer in `data.feature_count`. It is not calculated from a feature download. `fields_state` is `absent` when `data.fields` is null, `empty` when the list is empty, and `present` when names were read. Names stay in source order.
- No bulk export, no paging through `next`, and no feature geometry. `nz-arcgis` may read `arcgis.mfe.govt.nz` feature services; this skill does not. `data-govt-nz` searches `catalogue.data.govt.nz`. This is not the reserved `mfe-waste-data` skill.
- Live smoke is one search (`flood`, `page_size=1`) and one layer GET (`117733`). An outage, an empty flood search, or a licence that is not open attribution is not a pass.

## Errors

Malformed arguments, including a URL passed as the query, fail before a network call. Non-JSON and truncated JSON are schema failures. HTTP 429 is blocked and preserves `Retry-After` when the transport reports it. HTTP 503 and timeouts are upstream unavailable. HTTP 404 is not found, not an invented layer.
