---
name: nz-family-support
description: "Map New Zealand family support entitlement questions to official IRD, MSD, and WINZ sources without calculating eligibility. Use when the task involves Working for Families, Best Start, FamilyBoost, childcare help, Accommodation Supplement, MSD/WINZ handoffs, or finding the right official checker or programme page. Read-only; no private data collection, applications, or entitlement decisions."
license: MIT
compatibility: "Requires Python 3.10+"
metadata:
  thecolab.category: "social-policy"
  thecolab.source_owner: "Inland Revenue"
  thecolab.source_type: "mixed"
  thecolab.auth: "none"
  thecolab.access_mode: "documentation-workflow"
  thecolab.data_class: "public"
  thecolab.writes: "false"
  thecolab.browser: "false"
  thecolab.risk: "low"
  thecolab.cache_ttl: "24h"
  thecolab.schema_version: "1"
  thecolab.skill_type: "documentation-workflow"
  thecolab.pack: "nz-public-data"
  thecolab.source_url: "https://www.ird.govt.nz/support-for-families"
  thecolab.allowed_domains: "check.msd.govt.nz,www.ird.govt.nz,www.workandincome.govt.nz"
  thecolab.last_verified: "2026-07-19"
  thecolab.health: "healthy"
  thecolab.maintainer: "@adam91holt"
---

# NZ Family Support

Map high-level New Zealand family support questions to the official **IRD**, **MSD**, and
**Work and Income (WINZ)** pages/checkers that should be used next.

This skill is a **source map, not an entitlement calculator**. It does not collect
private details, decide eligibility, estimate payments, or submit applications.

## Use this when

- A user asks what official source covers **Working for Families** or family tax credits
- A user asks about **Best Start**, **FamilyBoost**, childcare help, or early childhood education costs
- A user asks about **Accommodation Supplement** or help with rent/board/housing costs
- A user is already dealing with **MSD/WINZ** and needs the IRD/MSD handoff for family support
- You need to send a user to an official private checker instead of gathering sensitive details in chat

## Do not use this for

- Calculating entitlement amounts, income thresholds, abatement, or payment dates
- Collecting names, IRD numbers, addresses, exact income, custody details, rent, or bank details
- Applying for payments, updating accounts, uploading documents, or contacting agencies
- Non-family welfare statistics — use `msd-benefits-nz` or `public-housing-nz` where appropriate

## Safe workflow

1. Classify the request at a high level: WFF, new baby/Best Start, childcare, housing, or MSD/WINZ handoff.
2. Run the CLI to retrieve official source links and handoff notes.
3. Give the user the relevant official pages/checkers and explain that eligibility must be checked there.
4. If the user shares private details, do not process them; redirect to the relevant official checker/page.

## Commands

```bash
cli=skills/nz-family-support/scripts/cli.py

# List all official source mappings
python3 $cli sources
python3 $cli sources --category childcare --json

# Search high-level wording; do not include private personal details
python3 $cli search "help with childcare fees" --json
python3 $cli search "rent accommodation supplement"

# Route common scenarios
python3 $cli pathways
python3 $cli pathway working-for-families --json
python3 $cli pathway on-benefit

# Show one official source
python3 $cli show ird-familyboost --json

# Optional live URL check of official pages
python3 $cli verify --all --json
```

### Main source IDs

- `ird-support-for-families`
- `ird-working-for-families`
- `ird-wff-msd-handoff`
- `ird-best-start`
- `ird-familyboost`
- `msd-checker`
- `msd-accommodation-supplement-checker`
- `winz-accommodation-supplement`
- `winz-childcare-subsidy`
- `winz-working-for-families`

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Official source map and safety notes: `references/source-map.md`

## Notes

- Prefer official checkers for personal circumstances: <https://check.msd.govt.nz/> and the relevant IRD/WINZ pages.
- Treat IRD/MSD/WINZ pages as authoritative and current; this repo only stores routing metadata.
- Use NZ English in summaries built from this output.
