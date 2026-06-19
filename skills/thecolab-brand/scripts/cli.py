#!/usr/bin/env python3
"""CLI for TheColab brand guidance."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PALETTE = {
    "ink": "#171412",
    "warm_off_white": "#F8F7F4",
    "white_card": "#FFFFFF",
    "deep_navy": "#31465F",
    "colab_blue": "#1688C7",
    "bright_blue": "#19A7E0",
    "kea_orange": "#C94A0A",
    "charcoal_body": "#4F4943",
    "muted_stone": "#6E6861",
    "soft_border": "#DDD8D0",
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
