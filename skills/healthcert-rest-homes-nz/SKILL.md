---
name: healthcert-rest-homes-nz
description: Query Ministry of Health certified aged-care rest-home provider data, facility pages, audit-report links, and certification caveats. Use when the task involves NZ rest-home certification, aged-care provider beds, legal entities, auditors, certificate end dates, audit report metadata, corrective-action page availability, or source caveats for bot-protected Ministry facility pages.
---

# HealthCert Rest Homes NZ

## Goal

Use a read-only CLI to inspect public Ministry of Health certified aged-care rest-home data and facility audit metadata.

## Use This When

- A user asks for certified New Zealand rest homes, aged-care facilities, bed counts, auditors, or legal provider names
- A workflow needs a respectful sample of Ministry certified-provider CSV rows by legal provider
- A user needs public Ministry facility page details or audit report links for one rest home
- A user needs clear blocked-source caveats for Ministry pages that return Cloudflare or edge-protection responses

## Do Not Use This For

- Bulk mirroring audit PDFs/DOCX files
- Private resident records, clinical records, complaints, or non-public certification data
- HealthCERT write actions, provider registration, or authenticated Ministry systems
- Inferring risk ratings or corrective-action status when the public page is blocked or does not publish those rows

## Preferred Workflow

1. Run `scripts/cli.py list --json` to fetch and filter the official certified aged-care CSV.
2. Use `sample --provider "Legal name" --json` for a small provider-level aggregation sample.
3. Use `facility "Premises name" --json` to fetch the public Ministry facility page when reachable.
4. Use `reports "Premises name" --json` to list public audit report links without downloading the documents.
5. If a facility page is blocked, report the returned `blocked` status, `source_url`, and the CSV fallback row instead of treating the facility as missing.

## CLI

Run with:

```bash
python3 skills/healthcert-rest-homes-nz/scripts/cli.py <command> [flags]
```

Commands:

- `list [--query TEXT] [--city CITY] [--provider NAME] [--limit N] [--json]` - fetch and filter the certified aged-care CSV
- `facility <slug-or-name> [--json]` - fetch one public facility page and return premise/provider/certification details when reachable
- `reports <slug-or-name> [--json]` - list public audit report links for one facility page
- `sample --provider NAME [--limit N] [--json]` - return a small provider-level CSV sample and summary totals

## Resources

- CLI entrypoint: `scripts/cli.py`
- Smoke test: `scripts/smoke_test.py`
- Source notes and caveats: `references/api-notes.md`

## Notes

- The CLI is read-only, keyless, and uses Python standard library modules plus the repo-local `lib/nzfetch.py` helper.
- The official CSV is the primary structured source for list/sample commands.
- Facility pages may return HTTP 403 to automated clients. The CLI classifies that as `blocked` and keeps the CSV-derived fallback metadata available.
- Audit report links are listed as metadata only; the skill does not download or parse PDFs/DOCX files.
