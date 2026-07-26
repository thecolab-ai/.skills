import importlib.util
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "skills" / "grocer-nz" / "scripts" / "cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("grocer_assets_cli", CLI_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GrocerAssetTests(unittest.TestCase):
    def test_manifest_constructs_deduplicated_urls_without_fetching(self):
        cli = load_cli()
        with (
            mock.patch.object(
                cli,
                "ensure_dependencies",
                side_effect=AssertionError("DuckDB must not start"),
            ),
            mock.patch.object(
                cli,
                "http_get",
                side_effect=AssertionError("assets must not fetch"),
            ),
        ):
            manifest = cli.asset_manifest(
                include_base=True,
                store_ids=[230, 230, 307],
                product_ids=[5452, 5452],
            )

        self.assertEqual(manifest["delivery"], "external_url")
        self.assertEqual(manifest["network_requests_made"], 0)
        self.assertEqual(
            [resource["kind"] for resource in manifest["resources"]],
            [
                "base_catalogue",
                "current_prices",
                "current_prices",
                "price_history",
            ],
        )
        self.assertEqual(
            manifest["resources"][0]["url"],
            "https://assets-prod.grocer.nz/public/base_v3.duckdb.br",
        )
        self.assertTrue(
            manifest["resources"][1]["url"].endswith(
                "/prices_per_store_v3/public_prices_230.parquet"
            )
        )
        self.assertTrue(
            manifest["resources"][3]["url"].endswith(
                "/price_history_v3/price_history_5452.parquet"
            )
        )

    def test_manifest_defaults_to_base_and_bounds_cardinality(self):
        cli = load_cli()
        manifest = cli.asset_manifest(
            include_base=False,
            store_ids=[],
            product_ids=[],
        )
        self.assertEqual(len(manifest["resources"]), 1)
        self.assertEqual(manifest["resources"][0]["kind"], "base_catalogue")
        with self.assertRaisesRegex(SystemExit, "at most 50"):
            cli.asset_manifest(
                include_base=False,
                store_ids=list(range(1, 52)),
                product_ids=[],
            )


if __name__ == "__main__":
    unittest.main()
