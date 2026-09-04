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
    canonical_input_url = (
        "https://www.safetravel.govt.nz/destinations/exampleland"
    )
    for noncanonical_input_url in (
        canonical_input_url + "/",
        "https://www.safetravel.govt.nz/destinations//exampleland",
        canonical_input_url + "?",
        canonical_input_url + "#",
        canonical_input_url + ";variant=1",
    ):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(cli, "fetch_text") as fetch,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main(["advice", noncanonical_input_url, "--json"])
        assert exit_code == 2
        assert stdout.getvalue() == ""
        assert json.loads(stderr.getvalue()) == {
            "error": "invalid_input",
            "message": (
                "destination URL must be a canonical www.safetravel.govt.nz "
                "destination URL"
            ),
        }
        fetch.assert_not_called()
    print(
        "[PASS] non-canonical destination URL variants fail before sitemap network I/O"
    )

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

    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            return_value=(sitemap_source, requested_url),
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["search", "exampleland", "--json"])
    assert exit_code == 6
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error": "source_schema_failure",
        "message": (
            "sitemap fetch did not resolve to the canonical SafeTravel sitemap URL"
        ),
    }
    print("[PASS] same-host sitemap redirects fail closed through the JSON CLI")

    mismatched_identity_source = replace_once(
        destination_source,
        "<h1>Exampleland</h1>",
        "<h1>Another Place</h1>",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=mismatched_identity_source,
        message_fragment="destination page identity",
    )
    print("[PASS] mismatched destination page identity fails closed through the CLI")

    punctuated_identity_source = replace_once(
        destination_source,
        "<h1>Exampleland</h1>",
        "<h1>São Tomé &amp; Príncipe</h1>",
    )
    punctuated_detail = cli.parse_destination_page(
        punctuated_identity_source,
        slug="sao-tome-and-principe",
        url=(
            "https://www.safetravel.govt.nz/destinations/"
            "sao-tome-and-principe"
        ),
    )
    assert punctuated_detail["destination"]["name"] == "São Tomé & Príncipe"
    print("[PASS] legitimate destination accents and punctuation preserve identity")

    malformed_body_source = replace_once(
        destination_source,
        "(level 2 of 4).&lt;/p&gt;",
        "(level 2 of 4).&lt;strong&gt;",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=malformed_body_source,
        message_fragment="advice body HTML fragment",
    )
    print("[PASS] malformed decoded advice body HTML fails closed through the CLI")

    self_closing_non_void_body_source = replace_once(
        destination_source,
        "(level 2 of 4).&lt;/p&gt;",
        "(level 2 of 4).&lt;strong/&gt;&lt;/p&gt;",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=self_closing_non_void_body_source,
        message_fragment="advice body HTML fragment",
    )
    print("[PASS] self-closing non-void advice body HTML fails closed")

    nested_body_source = replace_once(
        destination_source,
        (
            "&lt;p&gt;Exercise increased caution in Exampleland "
            "(level 2 of 4).&lt;/p&gt;"
        ),
        (
            "&lt;p&gt;&lt;strong&gt;Exercise increased caution&lt;/strong&gt; "
            "in Exampleland (level 2 of 4).&lt;br&gt;&lt;/p&gt;"
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=[
                (sitemap_source, cli.SITEMAP_URL),
                (nested_body_source, requested_url),
            ],
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["advice", "exampleland", "--json"])
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["data"]["advice_level"]["body"] == (
        "Exercise increased caution in Exampleland (level 2 of 4)."
    )
    print("[PASS] balanced nested and void advice body HTML remains accepted")

    contradictory_title_source = replace_once(
        destination_source,
        "&quot;title&quot;:&quot;Exercise increased caution&quot;",
        "&quot;title&quot;:&quot;Do not travel&quot;",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=contradictory_title_source,
        message_fragment="title disagreed",
    )
    print("[PASS] official advice title contradictions fail closed through the CLI")

    conflicting_body_source = replace_once(
        destination_source,
        "(level 2 of 4).&lt;/p&gt;",
        "(level 2 of 4), not level 4 of 4.&lt;/p&gt;",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=conflicting_body_source,
        message_fragment="conflicting level markers",
    )
    print("[PASS] conflicting secondary body level markers fail closed through the CLI")

    advice_container = re.search(
        r'^  <div id="js-advice-level-accordion"[^\n]+</div>\n',
        destination_source,
        re.MULTILINE,
    )
    assert advice_container
    duplicate_advice_sources = (
        replace_once(
            destination_source,
            advice_container.group(0),
            advice_container.group(0) * 2,
        ),
        replace_once(
            destination_source,
            '<section id="relatedNews">',
            (
                '<div id="js-accordion" data-content="[]"></div>\n'
                '<div id="js-accordion" data-content="[]"></div>\n'
                '<section id="relatedNews">'
            ),
        ),
    )
    for duplicate_advice_source in duplicate_advice_sources:
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=duplicate_advice_source,
            message_fragment="duplicate advice container",
        )
    print("[PASS] duplicate supported advice containers fail closed through the CLI")

    duplicate_json_member_sources = (
        replace_once(
            destination_source,
            "&quot;level&quot;:&quot;moderate&quot;",
            (
                "&quot;level&quot;:&quot;low&quot;,"
                "&quot;level&quot;:&quot;moderate&quot;"
            ),
        ),
        replace_once(
            destination_source,
            "&quot;isAutoExpanded&quot;:true",
            (
                "&quot;metadata&quot;:{&quot;token&quot;:1,"
                "&quot;token&quot;:2}"
            ),
        ),
    )
    for duplicate_json_member_source in duplicate_json_member_sources:
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=duplicate_json_member_source,
            message_fragment="duplicate object member",
        )
    print(
        "[PASS] duplicate advice JSON object members fail closed at every depth "
        "through the CLI"
    )

    duplicate_attribute_sources = (
        replace_once(
            destination_source,
            'id="js-advice-level-accordion"',
            'id="js-advice-level-accordion" ID="conflicting-advice-id"',
        ),
        replace_once(
            destination_source,
            " data-content='",
            ' DATA-CONTENT="[]" data-content=\'',
        ),
    )
    for duplicate_attribute_source in duplicate_attribute_sources:
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=duplicate_attribute_source,
            message_fragment="duplicate HTML attribute name",
        )
    print(
        "[PASS] duplicate HTML attribute names fail closed case-insensitively "
        "through the CLI"
    )

    unrelated_news_source = replace_once(
        destination_source,
        "<body>\n",
        (
            '<body>\n  <nav><a href="/news/site-announcement" '
            'aria-label="Site announcement">Site announcement</a></nav>\n'
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            cli,
            "fetch_text",
            side_effect=[
                (sitemap_source, cli.SITEMAP_URL),
                (unrelated_news_source, requested_url),
            ],
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = cli.main(["advice", "exampleland", "--json"])
    assert exit_code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert [item["title"] for item in payload["data"]["related_alerts_news"]] == [
        "Exampleland security update"
    ]
    assert "Site announcement" not in stdout.getvalue()
    print("[PASS] related news is scoped to the destination Related News surface")

    duplicate_news_surface_source = replace_once(
        destination_source,
        '<section id="relatedNews">',
        '<section id="relatedNews"></section>\n<section id="relatedNews">',
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=duplicate_news_surface_source,
        message_fragment="duplicate Related News surfaces",
    )
    print(
        "[PASS] ambiguous duplicate Related News surfaces fail closed through "
        "the CLI"
    )

    escaping_news_source = replace_once(
        destination_source,
        "/news/exampleland-security-update",
        "/news/../destinations/another-place",
    )
    assert_schema_error(
        cli,
        source=escaping_news_source,
        slug="exampleland",
        message_fragment="related-news URL",
    )
    print("[PASS] related-news dot segments cannot escape the /news/ namespace")

    for escaping_href in (
        "/news//exampleland-security-update",
        "/news/exampleland-security-update/",
        "/news/%2e%2e/destinations/another-place",
        "/news/%2E/destinations/another-place",
        "/news/%252e%252e/destinations/another-place",
        "/news/exampleland%2f..%2fdestinations/another-place",
        "/news/exampleland%252f..%252fdestinations/another-place",
        "/news/exampleland%5c..%5cdestinations/another-place",
        "/news/exampleland%255c..%255cdestinations/another-place",
        "/news/exampleland\\..\\destinations/another-place",
        "/news/exampleland%2Fupdate",
    ):
        encoded_escape_source = replace_once(
            destination_source,
            "/news/exampleland-security-update",
            escaping_href,
        )
        assert_cli_schema_error(
            cli,
            sitemap_source=sitemap_source,
            destination_source=encoded_escape_source,
            message_fragment="related-news URL",
        )
    print(
        "[PASS] non-canonical, encoded, and backslash related-news paths fail closed"
    )

    for suffix in ("?variant=1", "#variant", ";variant=1"):
        noncanonical_sitemap_source = replace_once(
            sitemap_source,
            requested_url,
            requested_url + suffix,
        )
        assert_cli_schema_error(
            cli,
            sitemap_source=noncanonical_sitemap_source,
            destination_source=destination_source,
            message_fragment="non-canonical destination URL",
        )
    print(
        "[PASS] sitemap query, fragment, and path parameters fail closed "
        "through the CLI"
    )

    root_destination_sitemap_source = replace_once(
        sitemap_source,
        "</urlset>",
        (
            "  <url><loc>https://www.safetravel.govt.nz/destinations"
            "</loc></url>\n"
            "  <url><loc>https://www.safetravel.govt.nz/destinations/"
            "cote-d%E2%80%99ivoire</loc></url>\n"
            "  <url><loc>https://www.safetravel.govt.nz/destinations/"
            "virgin-islands,-u-s</loc></url>\n</urlset>"
        ),
    )
    assert cli.parse_sitemap(root_destination_sitemap_source) == destinations
    print("[PASS] destination index URL is ignored without hiding malformed entries")

    malformed_destination_sitemap_source = replace_once(
        sitemap_source,
        "</urlset>",
        (
            "  <url><loc>https://www.safetravel.govt.nz/destinations/"
            "Bad-Slug</loc></url>\n</urlset>"
        ),
    )
    try:
        cli.parse_sitemap(malformed_destination_sitemap_source)
    except cli.SchemaError as exc:
        assert "malformed destination URL" in str(exc)
    else:
        raise AssertionError(
            "expected malformed destination-shaped sitemap URL rejection"
        )
    print("[PASS] malformed destination-shaped sitemap URLs fail closed")

    duplicate_slug_sitemap_source = replace_once(
        sitemap_source,
        "</urlset>",
        f"  <url><loc>{requested_url}</loc></url>\n</urlset>",
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=duplicate_slug_sitemap_source,
        destination_source=destination_source,
        message_fragment="duplicate destination slug",
    )
    print("[PASS] duplicate sitemap destination slugs fail closed through the CLI")

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

    bounded_depth_source = replace_once(
        destination_source,
        "&quot;isAutoExpanded&quot;:true",
        (
            "&quot;metadata&quot;:"
            + "[" * (cli.MAX_JSON_DEPTH + 1)
            + "null"
            + "]" * (cli.MAX_JSON_DEPTH + 1)
        ),
    )
    assert_cli_schema_error(
        cli,
        sitemap_source=sitemap_source,
        destination_source=bounded_depth_source,
        message_fragment="nesting depth",
    )
    print("[PASS] explicit JSON nesting limit is runtime-independent")

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
