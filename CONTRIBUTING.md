# Contributing Skills

This repo should be easy to extend and hard to mess up.

The standard is simple: narrow skills, strong trigger descriptions, lean `SKILL.md` files, and measurable validation.

## Quick start

```bash
# No install step required — this repo has zero Node.js dependencies.
# Everything is Python stdlib.

python3 scripts/new_skill.py my-skill --variant minimal
python3 scripts/validate_skill.py skills/my-skill

# Run skill smoke tests (Python, stdlib only — no extra deps)
python3 skills/<name>/scripts/smoke_test.py
```

## Core stance

- Prefer narrow, composable skills over giant umbrella skills
- Make the `description` field do the retrieval work
- Keep `SKILL.md` operational, not essay-like
- Move deep reference material into `references/`
- Put deterministic operations into `scripts/cli.py` as Python standard-library CLIs
- Keep helper CLI dependencies minimal: prefer Python stdlib; declare third-party deps in `requirements.txt` or PEP 723 `# /// script` inline metadata
- TypeScript/Node skill helpers are **not accepted** — all scripts must be Python
- Avoid per-skill doc clutter

## Getting past bot walls — the shared `nzfetch` helper

A lot of official NZ sources (data.govt.nz CKAN, councils, some government portals) sit behind
**Incapsula / Cloudflare** that block by **IP reputation** — a bare HTTP client gets an HTML
"checking your browser" challenge instead of the data. Don't hand-roll a fix per skill: use the
shared **`lib/nzfetch.py`** helper (stdlib only). It sends a browser-shaped User-Agent and, on a
block, **retries through a rotating proxy** when one is configured — a fresh IP per attempt clears
IP-reputation walls. With no proxy set it just does the single direct request, so nothing changes
on a clean network.

Import it from a skill's `scripts/cli.py` (it lives at the repo `lib/`, three parents up):

```python
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

def get(url):
    try:
        return nzfetch.fetch_json(url)          # also: fetch_bytes, fetch_text
    except nzfetch.Blocked as e:
        die(f"network error: {e}")              # transient block → smoke tests SKIP, not FAIL
    except nzfetch.FetchError as e:
        die(str(e))
```

`nzfetch.Blocked` is a subclass of `FetchError` — a transient bot-wall, **not** a dead source; a
skill should report it as a `network error` (so smoke tests skip) rather than crash. Keep your
smoke test's `is_network_failure()` markers including `blocked` / `network error`. A block includes
HTTP 403/429/451 **and 406** (Akamai's bot "Not Acceptable", seen on `aucklandcouncil.govt.nz`),
plus Incapsula/Cloudflare **and AWS-WAF (`goku`) challenge shells served at HTTP 200** — nzfetch
detects those by body fingerprint so they never slip through as an empty "success".

**Pick the right entry point — it decides challenge handling for you:**

- `fetch_text(url, ...)` for HTML / XML / RSS / CSV / any text. It **never** mis-reads a real page
  as a challenge, no matter what `accept` you pass — so you don't have to keep `json` out of your
  `accept` string.
- `fetch_json(url, ...)` for JSON APIs. An HTML interstitial where JSON was expected **is** treated
  as a challenge (and retried/rotated), because that's an API being walled.
- `fetch_bytes(url, ...) -> (body, content_type, final_url)` for binary/ZIP or when you need the
  final URL or content-type. Pass `expect_json=True/False` to control interstitial detection.

**Header-sensitive hosts.** A few sites (e.g. Interislander, Bluebridge) return a clean 200 to a
*bare* request but bot-wall the full Client-Hint / `Sec-Fetch-*` header set nzfetch sends by
default. For those, pass **`browser_headers=False`** — nzfetch then sends only a lean
`User-Agent + Accept + language + encoding` set (like plain `urllib`) while still giving you the
rotating-proxy fallback. All headers you pass via `headers={...}` (API keys, auth, Referer),
POST `data`/`method`, and a custom SSL `context=` are preserved through the proxy either way.

**Proxy config (all optional, all from the environment):**

| Env | Meaning |
|---|---|
| `FETCH_PROXY` / `HTTPS_PROXY` | Rotating proxy URL, e.g. `http://user:pass@host:port`. **A SECRET** — never hard-code, print, or commit it; `nzfetch` reads it from the env only. |
| `PROXY_RETRIES` | Retries through the proxy on a block, a fresh IP each (default 2). Raise it if a source is heavily flagged; lower keeps many-fetch skills fast under a tight timeout. |
| `NZFETCH_UA` | Override the User-Agent for a source that needs a specific one. |

Even without adopting `nzfetch`, any skill that uses `urllib` already **honours `HTTPS_PROXY`
natively**, so setting it routes that skill through the proxy — but only `nzfetch` adds the
retry-rotation + challenge-detection that makes the bypass *reliable*. Migrate a blocked skill by
swapping its `urllib.request.urlopen(...)` fetch for an `nzfetch` call as above (see
`skills/data-govt-nz` and `skills/eeca-ev-chargers-nz` for worked examples).

## Optional browser-assisted mode

Direct public HTTP/API calls are still the default. Only add a `--browser` mode when a public,
read-only website exposes useful data more reliably inside a real browser context than from a bare
HTTP client.

Use [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) for browser-assisted skills when it is
installed. Keep the dependency optional: import it only when `--browser` is requested, keep normal
validation and non-browser smoke tests working on clean hosts, and return a clear machine-readable
`cloakbrowser_not_installed` error if the user requested browser mode on a machine without it.

Browser-assisted mode is not CAPTCHA bypass tooling. If the site returns CAPTCHA, request-auth, bot
challenge, login, checkout, payment, booking, cart mutation, or protected account flows, stop and
return a blocked state or use a public fallback. Do not forge tokens, hold bookings, operate accounts,
or complete transactions.

Full convention: [`docs/browser-assisted-skills.md`](docs/browser-assisted-skills.md).

## Definition of done

A contribution is only ready when it passes all of these:

- `name` is specific, stable, and hyphenated
- `description` says what the skill does and when to use it
- `SKILL.md` is short enough to scan quickly
- The workflow is explicit
- Any referenced local files exist
- Any bundled scripts were actually run
- No placeholder text remains
- No duplicate guidance is split across `SKILL.md` and `references/`

## Repo rules

### 1. Build useful NZ-specific skills

The bar is not "must be government". The bar is "genuinely useful for New Zealand-specific tasks".

Good sources include:
- public and open datasets
- government APIs
- transport feeds
- pricing sources
- logistics or supply-chain data
- industry-specific NZ data sources
- other lawful, stable, agent-useful local data workflows

If the skill is useful, NZ-specific, and the source is legitimate, it belongs in scope.

### 2. Write narrow skills

Good:
- `auckland-transport-departures`
- `stats-nz-census`
- `linz-property-search`

Bad:
- `nz-data-helper`
- `tooling`
- `everything`

If a skill wants to teach three different jobs, split it.

### 3. Treat frontmatter as the trigger surface

The `description` is not marketing copy. It is routing logic in plain English.

Good:

```yaml
---
name: auckland-transport-departures
description: Query Auckland Transport real-time departures and stop data. Use when the task involves live bus or train departures, stop lookups, route timing, or GTFS-realtime transport data.
---
```

Bad:

```yaml
---
name: helper
description: Helps with NZ data.
---
```

### 4. Keep `SKILL.md` lean

Put the workflow, decision points, and non-obvious rules in `SKILL.md`.
Do not dump background theory, changelogs, setup diaries, or generic tutorials in there.

### 5. Keep one source of truth per concern

- Trigger logic lives in frontmatter
- Execution guidance lives in `SKILL.md`
- Deep detail lives in `references/`
- Reusable deterministic logic lives in `scripts/`
- Output resources or starter files live in `assets/`

Do not duplicate the same instructions in multiple places.

### 6. Ban clutter files inside skill folders

Do not add these unless they are runtime-critical:

- `README.md`
- `CHANGELOG.md`
- `NOTES.md`
- `IDEAS.md`

One clean central contribution guide beats a graveyard of side docs.

### 7. Make examples realistic

Good:
- `Fetch the latest departures for Britomart platform 2 and show them as JSON.`
- `Build a LINZ skill that can search parcels by title reference.`
- `Show me the latest NZ fuel summary and only flagged incoming diesel vessels.`

Bad:
- `Use this amazing skill to improve your project.`

### 8. If you ship a script, mention how to use it

A script with no invocation guidance is dead weight.
Reference the script from `SKILL.md` or a linked reference doc.

Python standard-library CLIs are the only accepted format for skill helpers. Do not add TypeScript or Node-based scripts. This repo has zero Node.js dependencies — no `npm install`, no `package.json`, no TypeScript toolchain. Document any required runtime, environment variable, or auth assumption in `SKILL.md`.

## Template variants

Use the scaffold that matches the job:

- `minimal` for narrow one-file skills
- `cli-workflow` for multi-step skills with references and scripts
- `tool-wrapper` for skills centered around a specific external CLI or API client

## Review checklist

- [ ] Skill name is specific and hyphenated
- [ ] Description includes clear triggers and boundaries
- [ ] `SKILL.md` is operational, not bloated
- [ ] References are linked directly from `SKILL.md`
- [ ] Script usage is documented
- [ ] No placeholder text remains
- [ ] No forbidden clutter files exist
- [ ] Validator passes cleanly

## Bottom line

Be opinionated in structure, strict in validation, and sparse in prose.
If the skill is hard to scan, vague to trigger, or padded with junk, it is not ready.
