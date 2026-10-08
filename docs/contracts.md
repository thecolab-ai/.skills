# Repository contracts

This document defines the machine-readable and policy contracts layered on top
of the public [Agent Skills specification](https://agentskills.io/specification).
Agent Skills format validation and TheColab repository-policy validation are
separate checks.

## Skill metadata

Every catalogue skill declares the following string values under `metadata`:

| Key | Purpose |
|---|---|
| `thecolab.category` | Search/filter category. |
| `thecolab.source_owner` | Agency, operator, project, or internal owner. |
| `thecolab.source_type` | `official`, `commercial`, `community`, `internal`, or `mixed`. |
| `thecolab.auth` | `none`, `api-key`, `personal-token`, `paid-credential`, or `mixed`. |
| `thecolab.access_mode` | Short description of the primary read surface. |
| `thecolab.data_class` | `public`, `personal`, or `internal`. |
| `thecolab.writes` | Quoted `true` or `false`; explicit source/account mutations and workflows whose primary purpose is creating or editing user artifacts count. Internal bounded caches do not. |
| `thecolab.browser` | Quoted `true` or `false`. |
| `thecolab.risk` | `low`, `medium`, or `high`. |
| `thecolab.cache_ttl` | Intended cache duration or `none`. |
| `thecolab.schema_version` | Result contract version; currently `1`. |
| `thecolab.skill_type` | Required-file/template contract. |
| `thecolab.pack` | One trust-based distribution pack. |
| `thecolab.source_url` | Canonical primary-source landing page or API root. |
| `thecolab.allowed_domains` | Comma-separated outbound host allowlist. |
| `thecolab.last_verified` | ISO date of the last meaningful verification. |
| `thecolab.health` | `healthy`, `degraded`, `gated`, or `untested`. |
| `thecolab.maintainer` | Account or team responsible for maintenance. |

Mutation-capable skills must also declare `thecolab.mutations` as a
comma-separated set of explicit operations. Legacy JavaScript helpers require
`thecolab.javascript_exception` with a concrete migration reason.

Skills that deliberately create user-visible local files also declare
`thecolab.local_output`. A bounded source-download option may remain a read-only
data connector when it does not modify the upstream source or become an artifact
authoring workflow. Cache files used only to implement a read command are covered
by `thecolab.cache_ttl`. HTTP `POST` is likewise not automatically a mutation
because many official search APIs use it for read-only queries.

## Result envelope

`scripts/run_skill.py` is the canonical machine interface while existing direct
CLI commands remain available for human and backwards-compatible use:

```bash
python3 scripts/run_skill.py stats-nz search population
```

It emits:

```json
{
  "schema_version": "1",
  "ok": true,
  "source": {
    "name": "Stats NZ",
    "url": "https://www.stats.govt.nz/",
    "retrieved_at": "2026-07-19T00:00:00Z"
  },
  "query": {"argv": ["search", "population", "--json"]},
  "data": [],
  "warnings": [],
  "blocked": false
}
```

Live results always include `source.url` and `source.retrieved_at`. Parser or
schema failures are failures, not empty successful datasets.

## Result provenance

New and substantially revised data commands include provenance in every `--json`
result. The default direct CLI success envelope is exactly:

```json
{
  "meta": {
    "source_url": "https://www.stats.govt.nz/",
    "publisher": "Stats NZ",
    "retrieved_at": "2026-10-08T00:00:00Z"
  },
  "results": []
}
```

`meta` is an object and `results` is always an array, including for a single
record or a successful query with no matches. Required provenance fields are
`source_url` (the public endpoint, download, or primary-source page used),
`publisher` (the source owner, not the skill author), and `retrieved_at` (ISO 8601
UTC, emitted with a trailing `Z`). Never include credentials in source URLs.
Include `licence` as a string when the source states its reuse terms; omit it
when unknown. The skill's code licence does not establish the data licence.
Include `latest_data` as a string when the source states a latest observation
date, reporting period, or update timestamp; preserve its precision and explain
its meaning in source notes. Do not infer freshness from the retrieval time.
For cached results, retain the original retrieval timestamp.

Envelope metadata applies to every contained record from that source. Mixed
sources add the same provenance fields to each record (or feature properties)
whose provenance differs. Existing record shapes may instead carry these fields
directly; adopting provenance does not require renaming established data fields.

The direct CLI error envelope uses the same `meta`, an empty `results` array,
and an `error` object:

```json
{
  "meta": {
    "source_url": "https://www.stats.govt.nz/",
    "publisher": "Stats NZ",
    "retrieved_at": "2026-10-08T00:00:00Z"
  },
  "results": [],
  "error": {
    "code": 5,
    "type": "upstream_unavailable",
    "message": "network error: source request timed out"
  }
}
```

For an error, `retrieved_at` records the attempted operation time, not a
successful retrieval. Emit one JSON object to stdout when `--json` is requested
and exit with the numeric `error.code` from the exit-code table below. Error
types are `invalid_input`, `missing_configuration`, `blocked`,
`upstream_unavailable`, `schema_failure`, and `unsupported_operation` for codes
2 through 7 respectively. Preserve an upstream `Retry-After` value in optional
`error.retry_after` when rate-limited. Do not report access, network, or parser
failures as successful empty results.

Spatial data commands accept `--bbox minLon,minLat,maxLon,maxLat` where spatial
filtering makes sense. Coordinates are WGS84 longitude then latitude in decimal
degrees. Require four finite values within longitude [-180, 180] and latitude
[-90, 90], with minLon < maxLon and minLat < maxLat. Reject boxes crossing the
antimeridian; callers can split those into two requests. Document whether
filtering uses intersection or containment and whether it occurs upstream or
locally. Convert source coordinates to WGS84 before emitting GeoJSON.
For a box beginning with a negative longitude, use the equals form, for example
`--bbox=-180,-90,180,90`, so argparse treats it as one value.

Offer `--format geojson` for spatial output. It emits a GeoJSON
`FeatureCollection` with top-level `type`, `features`, and the same provenance
`meta` as a foreign member, rather than wrapping GeoJSON inside `results`.
Coordinates follow GeoJSON longitude/latitude order. `--format geojson` implies
machine-readable output even without `--json`; errors retain the error envelope
above. Non-spatial commands do not need these spatial options.

This is an additive adoption contract: existing skills, CLI consumers, and the
schema-version-1 runner envelope above remain compatible. The runner retains
direct `meta`/`results` output under its `data` field. Skills already using the
runner envelope may add provenance in `meta` or their data records without
changing the existing `source` fields. Validation only warns when a CLI shows no
provenance fields; that advisory warning never becomes a `--strict` failure.
New scaffolds bundle `scripts/provenance.py` to build success/error envelopes and
provide optional spatial argument and GeoJSON helpers without dependencies.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Successful result |
| 2 | Invalid input |
| 3 | Missing configuration or credential |
| 4 | Access blocked or rate-limited |
| 5 | Upstream unavailable |
| 6 | Source schema or parser failure |
| 7 | Unsupported or unsafe operation |

## Contract and fixture tests

Each executable skill contains `scripts/test_contract.py`. Contract tests are
deterministic and must validate the CLI help surface, documented commands,
`--json`, Python compilation, declared outbound hosts, and required fixtures.
`tests/fixtures/contract.json` is an executable repository-policy sentinel: the
contract runner parses it and verifies its schema, skill identity, and absence
of credentials or personal data. Representative source/parser fixtures are
required when the skill parses a source format. Non-trivial or captured examples
live in `tests/fixtures/`; a minimal synthetic case may be inline when keeping it
beside the assertion makes the format clearer. Fixtures may contain only
synthetic or appropriately licensed public examples. Parser-fixture assertions
run in `scripts/smoke_test.py`; their failures cannot be skipped due to an
upstream outage.

Live probes remain bounded and outage-aware. Fixture assertions, contract
assertions, live assertions, skips, observed source health, and declared source
health are recorded independently. Static assertion sites are reported as
diagnostic evidence but are not relabelled as fixture assertions. A smoke test
that performs zero meaningful assertions reports `gated` or `untested`, never
`pass`.
