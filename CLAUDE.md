# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of standalone **Claude Code skills** focused on New Zealand — each wraps a free,
public data API (govt, transport, weather, retail, finance, etc.) behind a small Python CLI.
The repo is also published as a **Claude Code plugin marketplace** (`.claude-plugin/`).

It is its own git repository (`github.com/thecolab-ai/.skills`) nested inside the TheColabAI
monorepo — the monorepo root `CLAUDE.md` does **not** apply here. There is no shared build,
package manager, or runtime; skills are independent and self-contained.

## Repo layout

```
skills/<name>/          # each skill — kebab-case dir, one clear job
  SKILL.md              #   frontmatter + instructions (the index Claude reads)
  scripts/cli.py        #   the tool (main entry point)
  scripts/smoke_test.py #   end-to-end test, exits non-zero on failure
  references/*.md       #   heavy detail (API schemas, tables) loaded on demand
docs/                   # repo-wide conventions, including optional browser-assisted mode
scripts/                # repo tooling (see below)
templates/              # skill-minimal, skill-tool-wrapper, skill-cli-workflow
template/SKILL.md       # base template new_skill.py copies from
spec/agent-skills-spec.md  # the Agent Skills format spec
.claude-plugin/         # marketplace.json + plugin.json (plugin distribution)
.github/workflows/      # CI: validate-skills, smoke-tests, readme-skills
README.md               # public catalogue — the skill list here is CI-checked
```

## Working on skills

Use the repo tooling rather than editing by hand where possible:

```bash
python3 scripts/new_skill.py my-skill-name        # scaffold skills/my-skill-name/
python3 scripts/validate_skill.py skills/<name>   # validate structure + frontmatter (CI gate)
python3 skills/<name>/scripts/smoke_test.py        # run one skill's smoke test
bash scripts/run_all_smoke.sh                      # run every smoke test
python3 scripts/check_readme_skills.py             # verify README lists all skills (CI gate)
```

CI (`.github/workflows/`) runs `validate_skill.py --strict` on PRs (so **warnings fail the
build**), the smoke tests (self-hosted runner, `uv run`, secrets for the few key-gated skills,
also nightly at 06:00 NZST), and the README sync check. A new skill won't pass until it validates
clean, smoke-tests green, and is listed in README.md with a description matching its frontmatter.

## Conventions (match these exactly when adding or editing a skill)

These come from `CONTRIBUTING.md` and are enforced by validation/CI:

- **Self-contained & keyless.** Prefer free, public, no-auth APIs. If a key is unavoidable, the
  user supplies it via an environment variable — never commit secrets or bundle external state.
- **`SKILL.md` frontmatter:** exactly two keys — `name` (lowercase hyphen-case, must equal the
  directory name) and `description` (third person, starts with a trigger phrase, says *what it
  does* and *when to use it*, ≤ 1024 chars). Any other key is a validation error.
- **Progressive disclosure.** Keep `SKILL.md` under ~250 lines (the validator warns past that,
  and `--strict` CI turns the warning into a failure); push API schemas, large tables, and edge
  cases into `references/`. If `references/` or `scripts/` exists, `SKILL.md` must mention it.
- **Python 3 standard library only.** Use `urllib`, `json`, `argparse` — **not** `requests` or
  other pip deps, so skills run anywhere without installation.
- **`argparse` subcommands** for multi-action CLIs; every data command takes a `--json` flag
  (machine-readable for Claude) and otherwise prints clean human-readable text.
- **Timeout every network call** (10s default) and fail with a clear human message — not a stack
  trace — when an upstream API is down or rate-limited.
- **Optional browser-assisted mode:** direct HTTP/API stays preferred. If a public read-only site
  needs a real browser context, expose an explicit `--browser` flag using
  [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) when installed. Keep it optional, return
  machine-readable `cloakbrowser_not_installed` when unavailable, and treat CAPTCHA/request-auth as
  blocked states rather than bypass targets. See `docs/browser-assisted-skills.md`.
- **NZ English** in user-facing strings ("organisation", "colour"); American spelling in code.
- `smoke_test.py` exercises happy path + at least one edge case, is safe to re-run, and tolerates
  upstream flakiness (skip vs hard-fail on network errors).

When in doubt, copy the structure of an existing skill in `skills/` or start from
`templates/` — keep all skills behaving the same way.
