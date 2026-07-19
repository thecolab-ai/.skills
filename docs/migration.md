# Foundations migration

The repository is moving from a flat, manually indexed catalogue to validated
Agent Skills metadata and trust-based distribution packs.

## Current migration status

All 113 catalogue skills now carry the required metadata, trust-pack assignment,
outbound-domain declaration, canonical Python entry point, deterministic
contract test, and synthetic contract fixture. Passing those structural checks
does not by itself prove source-parser fixture coverage or live source health.

Use `scripts/run_smoke_tests.py --summary-json` to see explicit fixture, contract,
live, skip, and health evidence. Skills listed under
`without_fixture_assertions` still need a representative parser assertion when
they parse a source format; do not relabel a live check or the generic contract
sentinel as parser-fixture coverage. This source-specific migration continues in
priority order while the foundations checks prevent new unclassified work.

## Compatibility

- Existing skill folders and direct `scripts/cli.py` commands remain stable.
- Existing `--json` payloads remain available from direct CLIs during the
  migration.
- Use `scripts/run_skill.py` for the versioned common result envelope.
- The legacy `nz-skills` plugin remains an aggregate alias; new installations
  should choose the narrowest trust pack.
- User-configured proxy behaviour remains as documented in the access policy.

## Maintainer sequence

1. Add complete TheColab metadata and an outbound-domain allowlist.
2. Add deterministic parser fixtures and `scripts/test_contract.py`.
3. Make every documented data command expose `--json` and stable failure codes.
4. Ensure credentials are loaded only inside the command path that needs them.
5. Ensure every network call has an explicit timeout and every parser fails
   closed on source-schema changes.
6. Regenerate `skills.json`, `packs/*.json`, and the README. Review the static
   legacy aggregate plugin descriptors separately when compatibility changes.
7. Run the spec validator, repository-policy validator, all contract tests, and
   the bounded smoke suite.

The migration is complete only when every catalogue skill passes these checks;
green legacy smoke tests alone do not prove contract compliance.
