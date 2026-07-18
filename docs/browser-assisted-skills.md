# Browser-assisted skills

Most skills in this repository should stay as simple direct HTTP/API CLIs. Use browser assistance only when a public, read-only website exposes useful data more reliably from a real browser context than from a bare HTTP client.

Recommended browser runtime: [CloakBrowser](https://github.com/CloakHQ/CloakBrowser).

## When to add `--browser`

Add an explicit `--browser` flag when all of these are true:

- the data is public and no-login;
- direct HTTP/API calls are unreliable, incomplete, or frequently challenged;
- a real browser context materially improves access to the same public read-only workflow;
- the skill still has a useful non-browser fallback or a clear failure mode;
- the workflow stops before login, checkout, payment, booking, cart mutation, account actions, or protected user data.

Do not add `--browser` just because automation is possible. If the direct public endpoint works cleanly, prefer the simpler CLI.

## Required behaviour

Browser-assisted mode must be opt-in and honest:

- expose it as `--browser`, not as the default path;
- import/use CloakBrowser only when `--browser` is requested;
- keep normal validation and non-browser smoke tests working on clean hosts;
- if CloakBrowser is missing, return a clear machine-readable error named `cloakbrowser_not_installed`;
- include a human recommendation to install CloakBrowser or rerun without `--browser`;
- treat CAPTCHA, request-auth, bot challenges, or protected flows as blocked states, not puzzles to defeat;
- if the browser path is blocked but a public fallback exists, return the fallback data and include an explicit blocked flag such as `fare_search_blocked: true`.

This browser boundary is separate from the shared direct-HTTP policy. For public, unauthenticated resources, `lib/nzfetch.py` may use a user-configured proxy for routing and its existing bounded retry sequence. Browser-assisted mode must still stop at CAPTCHA, request-auth, login, protected-token, and account boundaries rather than trying to solve or cross them.

Example JSON error:

```json
{
  "error": "cloakbrowser_not_installed",
  "message": "Install CloakBrowser to use --browser.",
  "recommendation": "Recommend that the user installs CloakBrowser or reruns without --browser for the fallback path."
}
```

## Implementation sketch

Use this shape for Python CLIs:

```python
class CloakBrowserNotInstalled(RuntimeError):
    pass


def fetch_with_browser(...):
    try:
        from cloakbrowser import launch
    except ImportError as exc:
        raise CloakBrowserNotInstalled(
            "cloakbrowser_not_installed: install CloakBrowser to use --browser"
        ) from exc

    with launch(
        headless=True,
        timezone="Pacific/Auckland",
        locale="en-NZ",
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    ) as browser:
        page = browser.new_page()
        # Navigate public pages and read public data only.
```

For headless Linux servers, include safe Chromium flags where supported:

```text
--no-sandbox
--disable-dev-shm-usage
```

## Documentation requirements

When a skill offers `--browser`, document it in:

- `SKILL.md` usage/flags;
- `references/api-notes.md`, including the direct source, browser-assisted source, and blocked-state behaviour;
- smoke/validation notes, making clear that browser mode is optional for local clean-host validation but installed in GitHub Actions smoke runs.

Include the CloakBrowser repo link where useful: <https://github.com/CloakHQ/CloakBrowser>.

## CI and smoke tests

GitHub Actions smoke runs should install CloakBrowser and set:

```text
COLAB_SMOKE_WITH_CLOAKBROWSER=1
COLAB_SMOKE_USE_BROWSER=1
```

`scripts/run_all_smoke.sh` uses `uv run --with cloakbrowser` when `COLAB_SMOKE_WITH_CLOAKBROWSER=1`, so browser-assisted smoke tests can import CloakBrowser without making it a repo-wide static dependency.

For skills where `--browser` is the richer or more realistic path, the smoke test should prefer `--browser` when CloakBrowser is available or when `COLAB_SMOKE_USE_BROWSER=1` is set. It may still accept a clearly marked blocked/fallback state, for example `fare_search_blocked: true`, when the upstream site returns request-auth/CAPTCHA. A missing CloakBrowser install in CI should fail loudly rather than silently testing only the fallback.

## Security and ethics boundary

Browser-assisted mode is not CAPTCHA or authentication-bypass tooling. Do not ship code whose purpose is to solve challenges, forge protected tokens, cross login or account boundaries, place orders, hold bookings, or complete transactions.

The acceptable use case is narrow: use a real browser context to read the same public information a normal visitor can see, then convert that information into deterministic, agent-readable output.
