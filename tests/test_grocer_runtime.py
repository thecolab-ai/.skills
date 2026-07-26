import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "skills" / "grocer-nz" / "scripts" / "cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("grocer_runtime_cli", CLI_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return self


class FakeDuckDb:
    def __init__(self):
        self.calls = []
        self.connection = FakeConnection()

    def connect(self, database, *, config):
        self.calls.append((database, config))
        return self.connection


class GrocerRuntimeTests(unittest.TestCase):
    def test_native_worker_pools_are_bounded_before_duckdb_import(self):
        cli = load_cli()
        self.assertEqual(os.environ["OPENBLAS_NUM_THREADS"], "1")
        self.assertEqual(os.environ["OMP_NUM_THREADS"], "1")
        self.assertEqual(cli.DUCKDB_THREADS, 1)

    def test_connection_uses_bounded_memory_threads_and_spill_directory(self):
        cli = load_cli()
        fake = FakeDuckDb()
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            database = cache / "base_v3.duckdb"
            database.touch()
            with (
                mock.patch.object(cli, "duckdb", fake),
                mock.patch.object(cli, "CACHE", cache),
                mock.patch.object(cli, "ensure_dependencies"),
                mock.patch.object(cli, "base_db", return_value=database),
            ):
                connection = cli.con()

        self.assertIs(connection, fake.connection)
        _, config = fake.calls[0]
        self.assertEqual(config["threads"], "1")
        self.assertEqual(config["memory_limit"], "128MB")
        self.assertEqual(config["max_temp_directory_size"], "512MB")
        self.assertEqual(config["preserve_insertion_order"], "false")
        self.assertTrue(config["temp_directory"].endswith("duckdb-tmp"))
        self.assertIn("READ_ONLY", fake.connection.statements[0])


if __name__ == "__main__":
    unittest.main()
