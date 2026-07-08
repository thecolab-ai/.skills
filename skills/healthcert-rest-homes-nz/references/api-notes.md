# Ministry Rest-Home Certification Source Notes

Primary public sources:

- Rest-home listing page: `https://www.health.govt.nz/regulation-legislation/certification-of-health-care-services/certified-providers/rest-homes`
- Certified aged-care CSV: `https://www.health.govt.nz/system/files/LegalEntitySummaryAgedCare.csv`
- Facility page pattern: `https://www.health.govt.nz/regulation-legislation/certification-of-health-care-services/certified-providers/rest-homes/<slug>`

The listing page describes the CSV as a full list of certified providers in New Zealand. The public facility pages include premise details, certification/licence details, provider details, and audit report links. They may also include corrective-action material when issues from the latest audit are published.

## Blocked HTML Pages

Direct HTTP access to Ministry HTML pages can return HTTP 403 or edge-protection HTML even though the pages are public. The CLI uses the repo-local `nzfetch` helper and classifies those cases as `status: "blocked"` rather than treating the source as dead.

The CSV was reachable during implementation with `nzfetch`, while the listing HTML returned HTTP 403 from this environment. For that reason `list` and `sample` are CSV-backed; `facility` and `reports` return either parsed HTML metadata or an explicit blocked payload with CSV fallback details.

## Facility Matching

Facility slugs are derived from premise names using lowercase ASCII hyphen-case. For example, `Pomaria Rest Home` maps to:

`https://www.health.govt.nz/regulation-legislation/certification-of-health-care-services/certified-providers/rest-homes/pomaria-rest-home`

When a name is supplied, the CLI first checks the CSV for an exact or fuzzy premise-name match and then derives the facility page URL from that premise name. When a slug is supplied, it is used directly.

## Caveats

- The CSV has certification/provider fields but not full audit-report history.
- Facility pages are the public source for audit report links and any corrective-action sections.
- Audit report links are listed only; PDFs and DOCX files are not downloaded in normal commands.
- Do not infer risk ratings or action status when the facility page is blocked or does not publish those sections.
