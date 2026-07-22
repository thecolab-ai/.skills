#!/usr/bin/env python3
"""Deterministic parser-fixture assertions plus bounded outage-aware live probes."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).with_name("cli.py")
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_cli():
    spec = importlib.util.spec_from_file_location("wremo_cli", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    cli = load_cli()
    results: list[bool] = []

    def fixture_listing():
        page = (FIXTURES / "news-listing-sample.html").read_text(encoding="utf-8")
        items = cli.parse_news_listing(page)
        assert len(items) == 2
        assert items[0]["title"] == "Synthetic severe weather update – 21 July"
        assert items[0]["slug"] == "synthetic-severe-weather-update"
        assert items[0]["date"] == "2026-07-21"
        assert items[0]["url"].startswith("https://www.wremo.nz/news-and-events/")
        assert items[1]["date"] == "2024-09-06", "'Sept' month abbreviation must parse"

    def fixture_article():
        page = (FIXTURES / "article-sample.html").read_text(encoding="utf-8")
        article = cli.parse_article(page)
        assert article["title"] == "Synthetic severe weather update"
        assert len(article["paragraphs"]) == 2, "nav, breadcrumb and short fragments must be dropped"
        assert article["paragraphs"][0].startswith("Heavy rain is forecast")
        assert "emergency plans" in article["paragraphs"][1], "inline tags must be flattened"

    def fixture_degraded_card():
        page = (FIXTURES / "news-listing-sample.html").read_text(encoding="utf-8")
        # Remove the FIRST card's date div: its date must become None and the
        # second card must keep its own date — no cross-card stealing.
        broken = page.replace('<div class="article-date">21 July 2026</div>', "", 1)
        items = cli.parse_news_listing(broken)
        assert len(items) == 2, "both cards must survive a missing date"
        assert items[0]["date"] is None and items[0]["date_text"] is None
        assert items[1]["date"] == "2024-09-06", "second card must keep its own date"

    def fixture_dates():
        assert cli.parse_date("6 Sept 2024") == "2024-09-06"
        assert cli.parse_date("21 July 2026") == "2026-07-21"
        assert cli.parse_date("6 September 2024") == "2024-09-06", "full month names must parse"
        assert cli.parse_date("99 Jan 2024") is None, "impossible days must not emit pseudo-ISO"
        assert cli.parse_date("") is None and cli.parse_date("yesterday") is None

    results.append(check("fixture news listing parser", fixture_listing))
    results.append(check("fixture degraded card isolation", fixture_degraded_card))
    results.append(check("fixture article extraction and boilerplate filter", fixture_article))
    results.append(check("fixture NZ date parsing", fixture_dates))

    def live(name: str, args: list[str], assertion) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            if "network error" in stderr or "upstream unavailable" in stderr:
                print(f"[SKIP] live {name}: {stderr}")
                return
            raise AssertionError(f"exit {completed.returncode}: {stderr}")
        if not assertion(json.loads(completed.stdout)):
            raise AssertionError(f"live assertion for {name} evaluated false")
        print(f"[PASS] live {name}")

    def run_live() -> bool:
        try:
            live(
                "news listing",
                ["news", "--limit", "3", "--json"],
                lambda d: bool(d["items"]) and all(i["title"] and i["url"] for i in d["items"]),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] live probe: {exc}")
            return False

    results.append(run_live())
    if all(results):
        print("[PASS] live smoke assertions completed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
