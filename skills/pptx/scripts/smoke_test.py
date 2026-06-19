#!/usr/bin/env python3
"""Smoke test for the vendored Anthropic PPTX skill docs."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    root / "SKILL.md",
    root / "LICENSE.txt",
    root / "editing.md",
    root / "pptxgenjs.md",
    root / "scripts" / "cli.py",
    root / "scripts" / "thumbnail.py",
    root / "scripts" / "office" / "unpack.py",
    root / "scripts" / "office" / "pack.py",
]
missing = [str(p.relative_to(root)) for p in required if not p.exists()]
if missing:
    raise SystemExit(f"missing required PPTX skill files: {', '.join(missing)}")

skill = (root / "SKILL.md").read_text(encoding="utf-8")
for needle in ("markitdown", "pptxgenjs", "thumbnail.py", "editing.md"):
    if needle not in skill:
        raise SystemExit(f"SKILL.md missing expected guidance: {needle}")

print("[PASS] pptx skill docs and helper scripts present")
