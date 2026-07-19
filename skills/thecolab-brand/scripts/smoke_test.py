#!/usr/bin/env python3
"""Smoke test for TheColab brand skill docs."""
from pathlib import Path

skill = Path(__file__).resolve().parents[1] / "SKILL.md"
text = skill.read_text(encoding="utf-8")
for needle in ("TheColab.ai Brand Skill", "#1688C7", "Discover → Build → Operate", "Clawd", "scripts/cli.py"):
    if needle not in text:
        raise SystemExit(f"missing expected brand guidance: {needle}")
print("[PASS] contract thecolab-brand guidance present")
