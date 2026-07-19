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
