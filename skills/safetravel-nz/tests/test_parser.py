"""Deterministic parser assertions for synthetic SafeTravel source fixtures."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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
        "summary": "The New Zealand Government's official travel advice for Exampleland.",
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
            "body": "Do not travel to North Exampleland (level 4 of 4) because of armed conflict.",
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
