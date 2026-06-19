#!/usr/bin/env python3
"""Small stdlib CLI wrapper for the vendored Anthropic PPTX skill docs."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the vendored Anthropic PPTX skill guidance")
    parser.add_argument("section", nargs="?", choices=["summary", "skill", "editing", "pptxgenjs"], default="summary")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    files = {
        "skill": "SKILL.md",
        "editing": "editing.md",
        "pptxgenjs": "pptxgenjs.md",
    }
    if args.section == "summary":
        data = {
            "name": "pptx",
            "source": "https://github.com/anthropics/skills/tree/main/skills/pptx",
            "purpose": "Create, read, edit, and QA PowerPoint .pptx decks.",
            "guides": list(files.keys()),
        }
        print(json.dumps(data, indent=2) if args.json else "PPTX skill: use SKILL.md, editing.md, and pptxgenjs.md for deck work.")
        return

    content = read(files[args.section])
    if args.json:
        print(json.dumps({"section": args.section, "content": content}, indent=2))
    else:
        print(content)

if __name__ == "__main__":
    main()
