# Access Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing direct-first and rotating-proxy request flow while giving exhausted HTTP 429 responses a backward-compatible typed outcome, aligning repository access-policy documentation, and gating the helper with deterministic PR tests.

**Architecture:** Keep `lib/nzfetch.py` as the single stdlib HTTP policy boundary. Add an additive `RateLimited(Blocked)` exception and record the terminal status plus raw `Retry-After` value without changing attempt construction or success behaviour. Exercise the control flow with mocked stdlib HTTP objects, then run those tests from the existing validation workflow.

**Tech Stack:** Python 3 standard library (`urllib`, `unittest`, `unittest.mock`), Markdown, GitHub Actions YAML.

## Global Constraints

- Preserve one direct request followed by the existing configured number of proxy attempts.
- Preserve `FETCH_PROXY`, `HTTPS_PROXY`, lowercase `https_proxy`, `PROXY_RETRIES`, and `NZFETCH_UA` configuration.
- Do not add dependencies, proxy setup steps, CAPTCHA solving, authentication bypass, protected-token handling, account operation, or mutation workflows.
- Never include proxy URLs or credentials in errors or test output.
- Keep `RateLimited` catchable as `Blocked` for existing callers.
- Keep live sources out of deterministic tests.
- Use NZ English in user-facing prose.

---

### Task 1: Specify the shared fetch contract with failing unit tests

**Files:**
- Create: `tests/test_nzfetch.py`

**Interfaces:**
- Consumes: `nzfetch.fetch_bytes(url, ...)`, `nzfetch.Blocked`, proxy environment variables.
- Produces: deterministic contract tests for `nzfetch.RateLimited.retry_after`, unchanged proxy retry order, and safe configuration failures.

- [ ] **Step 1: Create deterministic response and HTTP-error helpers**

Add a stdlib-only test module that imports `lib/nzfetch.py`, clears all proxy-related environment variables in `setUp()`, restores them in `tearDown()`, and defines:

```python
class FakeResponse:
    def __init__(self, body=b"ok", content_type="text/plain", final_url="https://example.test/data"):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self._final_url = final_url

    def read(self):
        return self._body

    def geturl(self):
        return self._final_url


def http_error(status, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError(
        "https://example.test/data", status, "blocked", headers, None
    )
```

- [ ] **Step 2: Add tests that lock existing direct and proxy behaviour**

Cover one direct success, blocked direct access with no proxy, configured direct-then-proxy order, configured proxy success, exhausted 403/406/451 classification, and an HTTP-200 challenge body. Patch `urllib.request.urlopen()` and `urllib.request.build_opener()` so no test uses the network.

- [ ] **Step 3: Add failing tests for the new rate-limit contract**

Add tests asserting:

```python
with self.assertRaises(nzfetch.RateLimited) as caught:
    nzfetch.fetch_bytes("https://example.test/data")
self.assertIsInstance(caught.exception, nzfetch.Blocked)
self.assertEqual(caught.exception.retry_after, "120")
```

Test both a raw delta-seconds value and a missing header. With a configured proxy, assert the final 429 is classified only after the existing direct and proxy attempts have run.

- [ ] **Step 4: Add failing configuration and secret-safety tests**

Assert that non-integer `PROXY_RETRIES` raises an actionable `FetchError`, negative values retain the current minimum of one proxy retry, and no raised message contains `user:secret` from a configured proxy URL.

- [ ] **Step 5: Run the focused suite and verify RED**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_nzfetch.py' -v
```

Expected: existing-behaviour tests pass; tests referencing `RateLimited` and actionable invalid configuration fail because the new contract does not exist yet.

### Task 2: Implement the backward-compatible terminal outcomes

**Files:**
- Modify: `lib/nzfetch.py`
- Test: `tests/test_nzfetch.py`

**Interfaces:**
- Consumes: existing attempt loop and `Blocked` callers.
- Produces: `RateLimited(Blocked)` with `retry_after: str | None`; actionable `FetchError` for non-integer retry configuration.

- [ ] **Step 1: Add the minimal typed exception**

Immediately after `Blocked`, add:

```python
class RateLimited(Blocked):
    """Bounded attempts ended with HTTP 429.

    ``retry_after`` preserves the raw upstream header because it may be either
    delta-seconds or an HTTP date.
    """

    def __init__(self, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after
```

- [ ] **Step 2: Make retry-count parsing actionable without changing valid behaviour**

Extract parsing to:

```python
def _proxy_retries() -> int:
    raw = os.environ.get("PROXY_RETRIES", "3")
    try:
        return max(1, int(raw))
    except ValueError as exc:
        raise FetchError("PROXY_RETRIES must be an integer") from exc
```

Use it only when a proxy is configured, preserving the current default and minimum.

- [ ] **Step 3: Record the terminal status without changing attempt flow**

Initialise `last_status = None` and `last_retry_after = None` before the loop. For HTTP 403/406/429/451, keep the existing `continue`; also record `e.code` and, for 429, `e.headers.get("Retry-After")` when headers are available. Reset the terminal status for non-status network and challenge outcomes so the final classification reflects the last exhausted attempt.

- [ ] **Step 4: Raise `RateLimited` only when the final exhausted attempt was 429**

Before the existing `Blocked` raise, add:

```python
if last_status == 429:
    raise RateLimited(
        f"{url} rate-limited after {len(openers)} attempt(s); retry later.",
        retry_after=last_retry_after,
    )
```

Keep the general blocked message free of proxy configuration and credentials.

- [ ] **Step 5: Run the focused suite and verify GREEN**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_nzfetch.py' -v
```

Expected: all tests pass with no network access.

- [ ] **Step 6: Commit the runtime and test contract**

```bash
git add lib/nzfetch.py tests/test_nzfetch.py
git commit -m "feat(nzfetch): classify exhausted rate limits"
```

### Task 3: Align the repository access-policy documentation

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `COMPLAINTS.md`
- Modify: `docs/browser-assisted-skills.md`
- Modify: `lib/nzfetch.py`

**Interfaces:**
- Consumes: the approved policy in `docs/superpowers/specs/2026-07-19-access-foundations-design.md`.
- Produces: one consistent operator, contributor, browser, and runtime description.

- [ ] **Step 1: Update runtime documentation**

Describe the existing direct-first, bounded proxy attempts without promising that rotation will always clear a block. Document `RateLimited`, raw `retry_after`, and the distinction between exhausted rate limiting and other blocked outcomes.

- [ ] **Step 2: Align contributor guidance**

Retain the existing proxy environment-variable instructions and retry examples. Replace “bypass reliable” and guaranteed-clearing language with precise bounded-retry wording. State that proxy credentials are optional secrets and terminal outcomes must be explicit.

- [ ] **Step 3: Align public and operator-facing policy**

In `README.md` and `COMPLAINTS.md`, say that skills access public unauthenticated sources and may use a user-configured proxy for routing and bounded retries. Preserve the prohibitions on CAPTCHA solving, authentication bypass, token forgery, accounts, bookings, payments, and transactions. Keep the operator removal and rate-change process prominent.

- [ ] **Step 4: Align browser-assisted guidance**

Keep CAPTCHA and protected browser flows as blocked states. Clarify that this browser boundary does not remove the shared HTTP helper's user-configured proxy retry path for public unauthenticated resources.

- [ ] **Step 5: Check policy terminology and contradictions**

Run:

```bash
rg -n "bypass reliable|fresh IP.*clears|don't bypass|do not bypass|circumvent technical|rotating proxy|RateLimited|Retry-After" README.md CONTRIBUTING.md COMPLAINTS.md docs/browser-assisted-skills.md lib/nzfetch.py
```

Expected: no guarantee or absolute prohibition contradicts the approved policy; proxy, blocked, and rate-limited language is consistent.

- [ ] **Step 6: Commit the aligned policy**

```bash
git add README.md CONTRIBUTING.md COMPLAINTS.md docs/browser-assisted-skills.md lib/nzfetch.py
git commit -m "docs: align public-source access policy"
```

### Task 4: Gate deterministic foundation tests in pull requests

**Files:**
- Modify: `.github/workflows/validate-skills.yml`
- Test: `tests/test_nzfetch.py`

**Interfaces:**
- Consumes: stdlib unit tests in `tests/`.
- Produces: a PR validation step running `python3 -m unittest discover -s tests -p 'test_*.py' -v`.

- [ ] **Step 1: Add the deterministic test command to validation CI**

Add a named step after checkout and before or alongside strict skill validation:

```yaml
- name: Run deterministic foundation tests
  run: python3 -m unittest discover -s tests -p 'test_*.py' -v
```

- [ ] **Step 2: Run the exact CI command locally**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all deterministic tests pass.

- [ ] **Step 3: Commit the CI gate**

```bash
git add .github/workflows/validate-skills.yml
git commit -m "ci: gate shared fetch contract"
```

### Task 5: Verify the complete foundation slice and prepare the PR

**Files:**
- Review: all files changed from `origin/main`.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: evidence that the branch meets the approved spec and issue #181 slice.

- [ ] **Step 1: Run deterministic tests**

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: zero failures and zero errors.

- [ ] **Step 2: Run strict skill validation**

```bash
for skill in skills/*; do python3 scripts/validate_skill.py --strict "$skill" || exit 1; done
```

Expected: every skill validates successfully.

- [ ] **Step 3: Run the README catalogue check**

```bash
python3 scripts/check_readme_skills.py
```

Expected: README catalogue is in sync.

- [ ] **Step 4: Run the complete smoke harness**

```bash
bash scripts/run_all_smoke.sh
```

Expected: summary reports `FAIL: 0`; upstream-dependent skills may be `GATED` or skipped according to the existing harness contract.

- [ ] **Step 5: Review the final diff and policy coverage**

```bash
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git status --short --branch
```

Check every design acceptance criterion explicitly and confirm no proxy URL, credential, dependency, or unrelated skill change appears.

- [ ] **Step 6: Prepare the pull request**

Push `codex/platform-foundations-access-policy-181` and open a PR that links #181, states that current proxy rotation is intentionally retained, lists the deterministic verification evidence, and leaves outbound-domain allowlists plus the remaining foundation workstreams open.
