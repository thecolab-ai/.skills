# Access Foundations Design

## Context

Issue #181 identifies a contradiction between the repository's documented access policy and the shared `lib/nzfetch.py` runtime. The runtime deliberately tries a direct request first and, when a user has configured a proxy, retries blocked responses through that proxy. That behaviour is useful to repository users and is an intentional product decision.

This first foundation slice makes the policy and runtime contract consistent without removing or making proxy support harder to use.

## Goals

- Preserve the current direct-first, proxy-retry request flow.
- Keep proxy configuration limited to the existing, simple environment variables: `FETCH_PROXY` or `HTTPS_PROXY`, with optional `PROXY_RETRIES`.
- Distinguish an exhausted HTTP 429 response from other blocked responses while remaining backward compatible with existing callers.
- Preserve the upstream `Retry-After` value for callers that can schedule a later request.
- Make repository documentation accurately describe the implemented access behaviour and its boundaries.
- Add deterministic tests for the shared fetch helper and run them on every pull request.
- Demonstrate that the existing catalogue smoke-test harness still reports no failures after the change.

## Non-goals

- Removing, disabling, or adding setup steps to proxy support.
- Changing the number or order of direct and proxy attempts.
- Solving CAPTCHAs, forging protected tokens, automating authentication, or operating user accounts.
- Adding a per-skill outbound-domain allowlist before the metadata and validator contracts exist.
- Defining the catalogue-wide JSON result envelope or migrating individual skills to it.
- Implementing the remaining independent workstreams from issue #181 in this pull request.

## Access policy

The repository permits keyless access to public, unauthenticated sources. A skill may use a user-configured proxy for routing and `nzfetch` may retry its existing bounded set of block and challenge responses through that proxy. Proxy credentials remain optional secrets loaded from the environment and must never be committed, printed, or included in raised error messages.

The repository does not provide CAPTCHA solving, protected-token forgery, authentication bypass, transaction automation, or account operation. When the bounded direct and proxy attempts cannot obtain the public resource, the skill returns an explicit blocked or rate-limited outcome rather than fabricating an empty success.

Official APIs, feeds, and downloads remain preferred over HTML parsing. Operators may request removal, rate changes, attribution, or a different supported integration through the complaints process.

## Runtime design

### Existing request flow

`nzfetch.fetch_bytes()` continues to build its attempt list exactly as it does now:

1. Make one direct request.
2. If `FETCH_PROXY`, `HTTPS_PROXY`, or lowercase `https_proxy` is configured, append `PROXY_RETRIES` proxy attempts.
3. Retry HTTP 403, 406, 429, and 451 responses and recognised challenge bodies through the remaining attempts.
4. Return immediately when any attempt produces a usable response.

No new proxy flags, configuration files, dependencies, or interactive setup are introduced.

### Typed terminal outcomes

Add `RateLimited` as a subclass of `Blocked`. Existing callers that catch `Blocked` therefore continue to work unchanged, while new callers may catch `RateLimited` first when they need rate-limit-specific handling.

`RateLimited` carries a public `retry_after` attribute containing the raw upstream `Retry-After` header value or `None`. Raw preservation avoids incorrectly interpreting either delta-seconds or HTTP-date formats. Its message names the requested public URL and the number of bounded attempts, but never includes a proxy URL or credential.

During the existing attempt loop, `fetch_bytes()` records the terminal reason and the most recently observed `Retry-After` value. If the last exhausted response is HTTP 429, it raises `RateLimited`. Other exhausted block statuses and challenge bodies continue to raise `Blocked`. A successful later proxy attempt still returns the response normally.

`fetch_text()` and `fetch_json()` keep their existing interfaces and inherit this behaviour through `fetch_bytes()`.

## Documentation changes

- `README.md`: replace the absolute no-circumvention wording with the explicit access policy above, while retaining the prohibition on CAPTCHA, authentication, protected-token, account, booking, payment, and transaction automation.
- `CONTRIBUTING.md`: keep the existing proxy instructions, remove language that overstates bypass guarantees, document bounded outcomes, and explain `RateLimited.retry_after`.
- `COMPLAINTS.md`: make the operator-facing statement match the implemented public-source and user-configured-proxy policy.
- `docs/browser-assisted-skills.md`: keep browser challenges as blocked states and distinguish browser automation boundaries from the shared HTTP proxy retry path.
- `lib/nzfetch.py`: update module and API documentation to describe the same policy and typed outcomes without changing proxy configuration.

The per-skill outbound-domain allowlist remains explicitly deferred to the metadata/validator workstream because enforcing it before a declaration format exists would create a second temporary source of truth.

## Testing and CI

Create `tests/test_nzfetch.py` using only `unittest` and `unittest.mock`. Tests exercise real `nzfetch` control flow with deterministic fake responses and no live network calls.

Required cases:

- A direct success performs one request and returns its body and metadata.
- With no configured proxy, a blocked direct request raises `Blocked` after one attempt.
- With a configured proxy, a blocked direct request is followed by the configured number of proxy attempts.
- A successful proxy attempt returns normally.
- HTTP 403, 406, and 451 remain classified as `Blocked` after exhaustion.
- A recognised HTTP-200 challenge body remains classified as `Blocked` after exhaustion.
- An exhausted final HTTP 429 raises `RateLimited` and preserves `Retry-After`.
- `RateLimited` remains catchable as `Blocked` for backward compatibility.
- Invalid or negative retry configuration remains bounded and produces an actionable error rather than a traceback from configuration parsing.
- Raised messages do not contain configured proxy credentials.

Add `python3 -m unittest discover -s tests -p 'test_*.py'` to `.github/workflows/validate-skills.yml` so deterministic foundation tests gate every pull request alongside strict skill validation.

Before the pull request is declared ready:

1. Run the new deterministic unit suite.
2. Run strict catalogue validation.
3. Run the README catalogue check.
4. Run `bash scripts/run_all_smoke.sh` with the existing environment and require `FAIL: 0`. `PASS*` and `GATED` retain their current documented meanings.
5. Run focused proxy-enabled tests with a fake local proxy path; no real proxy credential is required for deterministic verification.

## Compatibility and rollout

The change is additive for callers. `RateLimited` subclasses `Blocked`, all public fetch function signatures remain unchanged, the existing environment variables retain their meanings, and the attempt order is unchanged. Skills that currently turn `Blocked` into a smoke-test skip continue to do so.

The pull request will link issue #181 and state that the issue's proposed removal of block-triggered proxy rotation is intentionally superseded by this design. The outbound-domain allowlist and the other seven foundation workstreams remain open for subsequent, independently reviewable pull requests.

## Acceptance criteria

- Proxy use remains opt-in and requires no configuration beyond the existing environment variables.
- Direct-first and bounded proxy retry behaviour is unchanged and covered by deterministic tests.
- Exhausted rate limiting has a backward-compatible typed outcome with the upstream `Retry-After` value.
- No error path leaks proxy URLs or credentials.
- README, contributing guidance, complaints guidance, browser-assisted guidance, and `nzfetch` describe one consistent policy.
- Deterministic foundation tests run on pull requests.
- Strict validation and README checks pass.
- The full smoke harness completes with zero failed skills.
