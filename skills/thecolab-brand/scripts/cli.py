#!/usr/bin/env python3
"""CLI for TheColab brand guidance."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PALETTE = {
    "ink": "#1C1917",
    "blue_grey": "#2E4057",
    "electric_cyan": "#0EA5E9",
    "cyan_dark": "#0284C7",
    "kea_orange": "#C2410C",
    "warm_cream": "#FBF9F6",
    "stone_text": "#44403C",
    "muted_stone": "#78716C",
    "white": "#FFFFFF",
}

MESSAGING = [
    "AI that works in the business",
    "Humans + agents together",
    "Fast pilots, real constraints",
    "Model-agnostic by design",
    "Community-backed learning",
]

def main() -> None:
    parser = argparse.ArgumentParser(description="Return TheColab.ai brand guidance")
    parser.add_argument("section", nargs="?", choices=["summary", "palette", "messaging", "skill"], default="summary")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if args.section == "palette":
        data = {"palette": PALETTE}
    elif args.section == "messaging":
        data = {"message_pillars": MESSAGING}
    elif args.section == "skill":
        data = {"content": (ROOT / "SKILL.md").read_text(encoding="utf-8")}
    else:
        data = {
            "name": "thecolab-brand",
            "positioning": "Practical NZ AI consultancy and community: sharp, warm, useful, operational.",
            "palette": PALETTE,
            "message_pillars": MESSAGING,
        }

    if args.json:
        print(json.dumps(data, indent=2))
    elif args.section == "palette":
        print("\n".join(f"{k}: {v}" for k, v in PALETTE.items()))
    elif args.section == "messaging":
        print("\n".join(f"- {m}" for m in MESSAGING))
    elif args.section == "skill":
        print(data["content"])
    else:
        print("TheColab.ai: practical NZ AI consultancy/community. Use sharp, warm, operational copy and the default palette from `palette`.")

if __name__ == "__main__":
    main()
