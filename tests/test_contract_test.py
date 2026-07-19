#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from contract_test import _help_subcommands, _static_hosts, audit_skill  # noqa: E402


class ContractTestTests(unittest.TestCase):
    def test_extracts_argparse_subcommands(self) -> None:
        help_text = """usage: cli.py [-h] {search,show,status} ...

positional arguments:
  {search,show,status}
    search  search records
"""
        self.assertEqual(_help_subcommands(help_text), ["search", "show", "status"])

    def test_does_not_treat_option_choices_as_subcommands(self) -> None:
        help_text = """options:
  --format {json,csv}  output format
"""
        self.assertEqual(_help_subcommands(help_text), [])

    def test_helper_files_are_checked_for_timeouts_and_lazy_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "fixture-skill"
            (skill / "scripts").mkdir(parents=True)
            (skill / "tests" / "fixtures").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                """---
name: fixture-skill
description: "Fixture skill for helper auditing."
metadata:
  thecolab.source_owner: "Fixture Agency"
  thecolab.source_url: "https://fixture.example.govt.nz/data"
  thecolab.allowed_domains: "fixture.example.govt.nz"
  thecolab.writes: "false"
  thecolab.health: "untested"
---

# Fixture skill
""",
                encoding="utf-8",
            )
            (skill / "scripts" / "cli.py").write_text(
                "#!/usr/bin/env python3\nprint('fixture')\n",
                encoding="utf-8",
            )
            (skill / "scripts" / "helper.py").write_text(
                """import os
import urllib.request

FIXTURE_API_KEY = os.getenv("FIXTURE_API_KEY")

def fetch():
    return urllib.request.urlopen("https://fixture.example.govt.nz/data")
""",
                encoding="utf-8",
            )
            (skill / "tests" / "fixtures" / "contract.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1",
                        "skill": "fixture-skill",
                        "fixture": "synthetic-contract-sentinel",
                        "contains_live_credentials": False,
                        "contains_personal_data": False,
                    }
                ),
                encoding="utf-8",
            )
            result = audit_skill(skill, run_help=False)
            self.assertTrue(any("network call has no explicit timeout" in error for error in result["errors"]))
            self.assertTrue(any("loaded lazily" in error for error in result["errors"]))

    def test_constant_built_url_hosts_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.py"
            path.write_text(
                """APP_ID = "ABC123"
HOST = f"{APP_ID.lower()}-dsn.algolia.net"
URL = f"https://{HOST}/1/indexes/query"
""",
                encoding="utf-8",
            )
            self.assertEqual(_static_hosts(path), {"abc123-dsn.algolia.net"})

    def test_partial_url_prefix_is_not_an_outbound_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.py"
            path.write_text('PREFIX = "https://www."\n', encoding="utf-8")
            self.assertEqual(_static_hosts(path), set())

    def test_runtime_credential_requires_non_none_auth_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "fixture-skill"
            (skill / "scripts").mkdir(parents=True)
            (skill / "tests" / "fixtures").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                """---
name: fixture-skill
description: "Fixture skill for authentication metadata auditing."
metadata:
  thecolab.source_owner: "Fixture Agency"
  thecolab.source_url: "https://fixture.example.govt.nz/data"
  thecolab.allowed_domains: "fixture.example.govt.nz"
  thecolab.auth: "none"
  thecolab.writes: "false"
  thecolab.health: "untested"
---

# Fixture skill
""",
                encoding="utf-8",
            )
            (skill / "scripts" / "cli.py").write_text(
                """#!/usr/bin/env python3
import os

def credential():
    return os.environ.get("FIXTURE_API_KEY")
""",
                encoding="utf-8",
            )
            (skill / "tests" / "fixtures" / "contract.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1",
                        "skill": "fixture-skill",
                        "fixture": "synthetic-contract-sentinel",
                        "contains_live_credentials": False,
                        "contains_personal_data": False,
                    }
                ),
                encoding="utf-8",
            )
            result = audit_skill(skill, run_help=False)
            self.assertTrue(any("contradict thecolab.auth=none" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
