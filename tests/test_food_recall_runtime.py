import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "nz-food-recalls" / "scripts"
CLI_PATH = SCRIPT_DIR / "cli.py"


def load_cli():
    sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("food_recall_runtime_cli", CLI_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FoodRecallRuntimeTests(unittest.TestCase):
    def test_partial_detail_failures_retain_list_rows_and_order(self):
        cli = load_cli()
        rows = [
            {"title": "first", "source_url": "https://www.mpi.govt.nz/first"},
            {"title": "second", "source_url": "https://www.mpi.govt.nz/second"},
        ]

        def detail(row, _retrieved_at):
            if row["title"] == "first":
                raise cli.nzfetch.FetchError("temporary failure")
            return {**row, "product_information": "available"}

        with mock.patch.object(cli, "_detail", side_effect=detail):
            detailed, failures = cli._details(rows, "2026-07-26T00:00:00Z")

        self.assertEqual(failures, 1)
        self.assertEqual([row["title"] for row in detailed], ["first", "second"])
        self.assertFalse(detailed[0]["detail_available"])
        self.assertEqual(detailed[1]["product_information"], "available")

    def test_all_detail_failures_raise_an_upstream_error(self):
        cli = load_cli()
        rows = [{"title": "first", "source_url": "https://www.mpi.govt.nz/first"}]
        with (
            mock.patch.object(
                cli,
                "_detail",
                side_effect=cli.nzfetch.FetchError("temporary failure"),
            ),
            self.assertRaises(cli.nzfetch.FetchError),
        ):
            cli._details(rows, "2026-07-26T00:00:00Z")

    def test_thread_admission_failure_retries_with_smaller_pool(self):
        cli = load_cli()
        rows = [
            {
                "title": f"notice {index}",
                "source_url": f"https://www.mpi.govt.nz/notice-{index}",
            }
            for index in range(5)
        ]
        real_executor = cli.concurrent.futures.ThreadPoolExecutor
        attempts = []

        def executor(*, max_workers):
            attempts.append(max_workers)
            if len(attempts) == 1:
                raise RuntimeError("can't start new thread")
            return real_executor(max_workers=max_workers)

        with (
            mock.patch.object(
                cli,
                "_detail",
                side_effect=lambda row, _retrieved_at: {
                    **row,
                    "detail_available": True,
                },
            ),
            mock.patch.object(
                cli.concurrent.futures,
                "ThreadPoolExecutor",
                side_effect=executor,
            ),
        ):
            detailed, failures = cli._details(rows, "2026-07-26T00:00:00Z")

        self.assertEqual(attempts, [5, 4])
        self.assertEqual(failures, 0)
        self.assertEqual(len(detailed), 5)


if __name__ == "__main__":
    unittest.main()
