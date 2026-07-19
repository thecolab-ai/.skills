#!/usr/bin/env python3
"""Smoke test for TheColab brand skill docs."""
import importlib.util
import sys
from pathlib import Path

skill = Path(__file__).resolve().parents[1] / "SKILL.md"
text = skill.read_text(encoding="utf-8")
for needle in ("TheColab.ai Brand Skill", "#1688C7", "Discover → Build → Operate", "Clawd", "scripts/cli.py"):
    if needle not in text:
        raise SystemExit(f"missing expected brand guidance: {needle}")
cli_path = skill.parent / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("thecolab_brand_cli", cli_path)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)
assert cli.PALETTE["colab_blue"] == "#1688C7" and "Humans + agents together" in cli.MESSAGING
print("[PASS] fixture brand palette and messaging data")
print("[PASS] contract thecolab-brand guidance present")
