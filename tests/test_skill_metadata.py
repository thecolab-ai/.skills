#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from skill_metadata import FrontmatterError, parse_frontmatter_text  # noqa: E402


class SkillMetadataTests(unittest.TestCase):
    def test_current_optional_fields_and_nested_string_metadata(self) -> None:
        document = parse_frontmatter_text(
            """---
name: test-skill
description: Test a source. Use for contract validation.
license: MIT
compatibility: Requires Python 3.10+
metadata:
  thecolab.writes: "false"
  thecolab.schema_version: "1"
allowed-tools: Read Bash(git:*)
---

# Test
"""
        )
        self.assertEqual(document.fields["name"], "test-skill")
        self.assertEqual(document.metadata["thecolab.writes"], "false")
        self.assertEqual(document.metadata["thecolab.schema_version"], "1")
        self.assertIn("# Test", document.body)

    def test_unquoted_yaml_boolean_is_not_treated_as_string(self) -> None:
        document = parse_frontmatter_text(
            """---
name: test-skill
description: Test
metadata:
  thecolab.writes: false
---
body
"""
        )
        self.assertIs(document.fields["metadata"]["thecolab.writes"], False)

    def test_duplicate_metadata_key_fails(self) -> None:
        with self.assertRaisesRegex(FrontmatterError, "duplicate metadata key"):
            parse_frontmatter_text(
                """---
name: test-skill
description: Test
metadata:
  owner: "one"
  owner: "two"
---
body
"""
            )


if __name__ == "__main__":
    unittest.main()
