# Source notes

- Primary owner: Water Services Authority — Taumata Arowai
- Public register: https://hinekorako.taumataarowai.govt.nz/publicregister/supplies/
- Declared outbound host: `hinekorako.taumataarowai.govt.nz`
- Access mode: public Power Pages grid and server-rendered read-only detail pages
- Authentication: none
- Last verified: 2026-07-19

## Implemented surface

The official listing exposes a public Power Pages grid with Supply ID, Supply Name, Supply Type,
Community and a detail-record UUID. The connector reads the page's signed grid configuration,
obtains the portal's public anti-forgery token and makes the same bounded JSON request as the
browser. Exact supply-ID lookup follows the public detail URL and parses registration status,
population, region, territorial authority, regional public-health service, exemptions and linked
public documents where those fields are published. Exact case-insensitive supply-name lookup also
follows the detail record. Supplier results are produced only from supplier/owner/operator
relationships explicitly published on those details and include related supplies; a bounded scan
with no published relationship returns exit 7 instead of relabelling supplies as suppliers.

The portal states that some supplies need not register until 2028, lapsed records may not be up
to date, and information can be withheld. Every result therefore includes explicit
`what_this_does_not_prove` caveats. Missing fields/documents remain missing and are never converted
to non-compliance. The `documents` command resolves only an exact case-insensitive supply ID or
name from a bounded 50-row portal search. Exact matches always return the document result shape;
fuzzy-only matches return an empty result and are never returned as raw supply summaries. The public pages do not expose coordinates or authoritative service-area
geometry, so `near` returns exit code 7 instead of guessing.

The deterministic fixtures cover listing fields, detail fields, an absent checkbox, documents,
provenance and caveats. The live smoke test performs a bounded ID query and detail retrieval.
