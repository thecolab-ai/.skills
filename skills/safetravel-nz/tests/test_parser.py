"""Deterministic parser assertions for synthetic SafeTravel source fixtures."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / "scripts" / "cli.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("safetravel_nz_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def assert_schema_error(cli, *, source: str, slug: str, message_fragment: str) -> None:
    try:
        cli.parse_destination_page(
            source, slug=slug, url=f"https://www.safetravel.govt.nz/destinations/{slug}"
        )
    except cli.SchemaError as exc:
        assert message_fragment in str(exc)
    else:
        raise AssertionError(f"expected SchemaError containing {message_fragment!r}")


def replace_once(source: str, old: str, new: str) -> str:
    assert source.count(old) >= 1, f"fixture mutation target missing: {old!r}"
    return source.replace(old, new, 1)


def assert_cli_schema_error(
    cli, *, sitemap_source: str, destination_source: str, message_fragment: str
) -> None:
    requested_url = "https://www.safetravel.govt.nz/destinations/exampleland"
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=[
                (sitemap_source, cli.SITEMAP_URL),
                (destination_source, requested_url),
            ],
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["advice", "exampleland", "--json"])
    assert exit_code == 6
    assert stdout.getvalue() == ""
    assert "Traceback" not in stderr.getvalue()
    error_payload = json.loads(stderr.getvalue())
    assert error_payload["error"] == "source_schema_failure"
    assert message_fragment in error_payload["message"]


def main() -> int:
    cli = load_cli()

    destinations = cli.parse_sitemap(read_fixture("sitemap.xml"))
    assert destinations == [
        {
            "name": "Another Place",
            "slug": "another-place",
            "url": "https://www.safetravel.govt.nz/destinations/another-place",
            "sitemap_last_modified": None,
        },
        {
            "name": "Exampleland",
            "slug": "exampleland",
            "url": "https://www.safetravel.govt.nz/destinations/exampleland",
            "sitemap_last_modified": "2026-08-15",
        },
    ]
    print("[PASS] fixture sitemap destination catalogue parser")

    detail = cli.parse_destination_page(
        read_fixture("destination-page.html"),
        slug="exampleland",
        url="https://www.safetravel.govt.nz/destinations/exampleland",
    )
    assert detail["destination"] == {
        "name": "Exampleland",
        "slug": "exampleland",
        "url": "https://www.safetravel.govt.nz/destinations/exampleland",
        "page_updated": "15 August 2026",
        "summary": (
            "The New Zealand Government's official travel advice for "
            "Exampleland."
        ),
    }
    assert detail["advice_level"]["number"] == 2
    assert detail["advice_level"]["level"] == "moderate"
    assert detail["advice_level"]["title"] == "Exercise increased caution"
    assert detail["regional_cautions"] == [
        {
            "title": "Do not travel",
            "subtitle": "to North Exampleland",
            "level": "extreme",
            "number": 4,
            "last_updated": "29 July 2026",
            "still_current_at": "03 September 2026",
            "body": (
                "Do not travel to North Exampleland (level 4 of 4) because of "
                "armed conflict."
            ),
        }
    ]
    assert detail["related_alerts_news"] == [
        {
            "title": "Exampleland security update",
            "updated": "29 July 2026",
            "url": "https://www.safetravel.govt.nz/news/exampleland-security-update",
            "summary": "Official update for travellers.",
        }
    ]
    print(
        "[PASS] fixture destination advice, regional caution, and related-news parser"
    )

    assert cli.normalise_destination("Exampleland") == "exampleland"
    assert (
        cli.normalise_destination(
            "https://www.safetravel.govt.nz/destinations/another-place"
        )
        == "another-place"
    )
    print("[PASS] fixture destination input normalisation")

    assert_schema_error(
        cli,
        source=read_fixture("destination-page-regional-only.html"),
        slug="regional-only",
        message_fragment="exactly one non-regional primary item",
    )
    print("[PASS] regional-only advice data is rejected")

    assert_schema_error(
        cli,
        source=read_fixture("destination-page-multiple-primary.html"),
        slug="multiple-primary",
        message_fragment="exactly one non-regional primary item",
    )
    print("[PASS] multiple primary advice data is rejected")

    assert_schema_error(
        cli,
        source=read_fixture("destination-page-contradictory-level.html"),
        slug="contradictory-level",
        message_fragment="advice-level data disagreed",
    )
    print("[PASS] contradictory advice level data is rejected")

    sitemap_source = read_fixture("sitemap.xml")
    destination_source = read_fixture("destination-page.html")
    requested_url = "https://www.safetravel.govt.nz/destinations/exampleland"

    for constant in ("NaN", "Infinity", "-Infinity"):
        malformed_json_source = replace_once(
            destination_source,
            "&quot;isAutoExpanded&quot;:true",
            (
                "&quot;metadata&quot;:{&quot;deep&quot;:["
                f"{constant}]}}"
            ),
        )
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=malformed_json_source,
            message_fragment="not valid JSON",
        )
    print("[PASS] non-standard JSON constants are rejected at every depth")

    overflowed_number_source = replace_once(
        destination_source,
        "&quot;isAutoExpanded&quot;:true",
        "&quot;metadata&quot;:{&quot;deep&quot;:[1e309]}",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=overflowed_number_source,
        message_fragment="not valid JSON",
    )
    print("[PASS] overflowed JSON numbers cannot produce non-finite values")

    deeply_nested_source = replace_once(
        destination_source,
        "&quot;isAutoExpanded&quot;:true",
        "&quot;metadata&quot;:" + "[" * 3000 + "null" + "]" * 3000,
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=deeply_nested_source,
        message_fragment="nesting depth",
    )
    print("[PASS] deeply nested advice JSON is rejected cleanly")

    unclosed_source = re.sub(r"</[^>]+>", "", destination_source)
    assert unclosed_source != destination_source
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=unclosed_source,
        message_fragment="destination page HTML",
    )
    print("[PASS] materially unclosed destination HTML fails closed")

    unclosed_head_source = replace_once(destination_source, "</head>", "")
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=unclosed_head_source,
        message_fragment="destination page HTML",
    )
    print("[PASS] an individually unclosed structural element is rejected")

    missing_regional_source = replace_once(
        destination_source, ",&quot;regional&quot;:false", ""
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=missing_regional_source,
        message_fragment="regional classification",
    )
    print("[PASS] missing regional classification is rejected")

    for invalid_boolean in ("&quot;false&quot;", "0", "null"):
        invalid_regional_source = replace_once(
            destination_source,
            "&quot;regional&quot;:false",
            f"&quot;regional&quot;:{invalid_boolean}",
        )
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=invalid_regional_source,
            message_fragment="regional classification",
        )
    print("[PASS] regional classification rejects truthy and falsey coercions")

    boolean_title_source = replace_once(
        destination_source,
        "&quot;title&quot;:&quot;Exercise increased caution&quot;",
        "&quot;title&quot;:true",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=boolean_title_source,
        message_fragment="invalid title field",
    )
    print("[PASS] boolean advice strings are rejected instead of coerced")

    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=[
                (sitemap_source, cli.SITEMAP_URL),
                (
                    destination_source,
                    "https://www.safetravel.govt.nz/destinations/another-place",
                ),
            ],
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["advice", "exampleland", "--json"])
    assert exit_code == 6
    assert stdout.getvalue() == ""
    assert '"ok": true' not in stderr.getvalue().casefold()
    assert json.loads(stderr.getvalue()) == {
        "error": "source_schema_failure",
        "message": (
            "destination fetch resolved to a different canonical destination: "
            "requested 'exampleland', received 'another-place'"
        ),
    }
    print(
        "[PASS] cross-destination redirects fail closed without a mixed success "
        "response"
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=[
                (sitemap_source, cli.SITEMAP_URL),
                (destination_source, requested_url),
            ],
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["advice", "exampleland", "--json"])
    assert exit_code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is True
    assert payload["query"]["destination"] == "exampleland"
    assert payload["source"]["url"] == requested_url
    assert payload["data"]["destination"]["slug"] == "exampleland"
    assert payload["data"]["destination"]["url"] == requested_url
    assert payload["data"]["advice_level"]["number"] == 2
    assert payload["data"]["advice_level"]["level"] == "moderate"
    print(
        "[PASS] exact canonical destination keeps coherent advice and safety semantics"
    )

    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=cli.nzfetch.RateLimited("synthetic 429", retry_after="120"),
        ),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["search", "exampleland", "--json"])
    assert exit_code == 4
    error_payload = json.loads(stderr.getvalue())
    assert error_payload == {
        "error": "rate_limited",
        "message": "source rate-limited: synthetic 429; retry after 120",
        "retry_after": "120",
    }
    print("[PASS] rate-limited JSON errors preserve raw retry-after values")

    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=cli.nzfetch.RateLimited("synthetic 429", retry_after="120"),
        ),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["search", "exampleland"])
    assert exit_code == 4
    assert "retry after 120" in stderr.getvalue()
    assert "rate_limited" not in stderr.getvalue()
    print("[PASS] rate-limited human errors stay actionable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
