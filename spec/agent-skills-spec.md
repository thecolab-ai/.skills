# Agent Skills Spec

The canonical Agent Skills specification lives at:

<https://agentskills.io/specification>

The repository validators support the required `name` and `description` fields
plus the current optional `license`, `compatibility`, `metadata`, and
experimental `allowed-tools` fields. `scripts/validate_agent_spec.py` checks
only that public format. `scripts/validate_repo_policy.py` separately checks
TheColab metadata, files, trust, and operational policy.

## Repo-specific stance

This repository follows the public Agent Skills spec, with a few house rules for contribution quality:

- keep skills narrow and composable
- make the `description` field explicit about what the skill does and when to use it
- keep `SKILL.md` operational and lean
- move deep detail into `references/`
- put deterministic helpers in `scripts/`
- avoid clutter files inside skill folders

Scope note:
This repo is for useful New Zealand-specific data and workflows. Public and open data is strongly encouraged, but the scope is broader than government-only sources.

For repo rules, use [../CONTRIBUTING.md](../CONTRIBUTING.md).
For the metadata and runtime schema, use [../docs/contracts.md](../docs/contracts.md).

This repo intentionally does not vendor Anthropic's example skills. We follow the shared standard, but keep the content and examples specific to TheColab and New Zealand-specific workflows.
