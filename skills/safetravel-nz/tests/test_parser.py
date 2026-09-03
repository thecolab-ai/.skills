#!/usr/bin/env python3
"""Deterministic parser assertions for synthetic SafeTravel source fixtures."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


def main() -> int:
    cli = load_cli()
    destinations = cli.parse_sitemap((FIXTURES / "sitemap.xml").read_text(encoding="utf-8"))
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
        (FIXTURES / "destination-page.html").read_text(encoding="utf-8"),
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
    print("[PASS] fixture destination advice, regional caution, and related-news parser")

    assert cli.normalise_destination("Exampleland") == "exampleland"
    assert cli.normalise_destination("https://www.safetravel.govt.nz/destinations/another-place") == "another-place"
    print("[PASS] fixture destination input normalisation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
