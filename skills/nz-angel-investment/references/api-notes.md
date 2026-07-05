# NZ angel investment source notes

## NZGCP Young Company Finance

Primary public source pages:

- NZGCP report index: <https://www.nzgcp.co.nz/about-us/news-and-media/view/reports>
- NZGCP startup investment magazine/YCF filter: <https://www.nzgcp.co.nz/about-us/news-and-media/view/reports/startup-investment-magazine>

Observed YCF PDF URLs include:

- `https://www.nzgcp.co.nz/assets/Media/NZGCP-YCF-Autumn-2026.pdf`
- `https://www.nzgcp.co.nz/assets/Media/NZGCP-YCF-Spring-2025-v2.pdf`
- `https://www.nzgcp.co.nz/assets/Media/NZGCP-YCF-Autumn-2025.pdf`
- `https://www.nzgcp.co.nz/assets/Media/YCF-Spring-2024.pdf`

The CLI keeps a curated YCF index and can refresh links from the NZGCP report page with `ycf list --discover`. For `ycf get 2025`, the headline values are curated from NZGCP YCF Autumn 2026:

- 166 funded deals.
- $754 million invested.
- 47 new companies funded.

Stage-split values are not exposed as extracted metrics because they are chart/table values in PDFs. With Python standard library only, reliable deep PDF layout extraction is not practical. Treat records marked `source_discovery_only` as source links, not extracted datasets.

## NZGCP annual and ecosystem reports

Primary public source pages:

- All reports: <https://www.nzgcp.co.nz/about-us/news-and-media/view/reports>
- Annual reports: <https://www.nzgcp.co.nz/about-us/news-and-media/view/reports/annual-report>

Observed report URLs include:

- `https://www.nzgcp.co.nz/assets/Media/NZGCP-Annual-Report-2025-FINAL.pdf`
- `https://www.nzgcp.co.nz/assets/Media/NZGCP-Annual-Report-2024.pdf`
- `https://www.nzgcp.co.nz/assets/Media/NZGCP-Annual-Report-2023_FINAL.pdf`
- `https://www.nzgcp.co.nz/assets/Media/New-Zealand-2025-report.pdf`

`nzgcp-reports` parses report cards from the public NZGCP HTML listing and returns PDF titles, URLs, filenames, inferred years, and coarse publication kinds. It does not parse PDF contents.

## Angel Association NZ members

Primary public source:

- Members page: <https://www.angelassociation.co.nz/members/>

The members page is a WordPress/MyListing directory. The page includes a public `ajax_nonce`; the browser frontend calls `/?mylisting-ajax=1&action=get_listings&security=<nonce>`. The CLI follows the same read-only JSON endpoint and parses returned listing-preview HTML cards.

Returned fields are deliberately conservative:

- `name` from the card title.
- `url` from the listing link.
- `regions` and `region_slugs` from listing CSS classes.
- `focus` from the short card tagline.
- `email` only when visible in the card.
- `locations` from the card's `data-locations` JSON.

If the MyListing frontend changes its card markup, parsing may need updating.

## Angel Association NZ investment publications

Primary public source:

- Investment publications page: <https://www.angelassociation.co.nz/resources/investment-publications/>
- WordPress page REST record: <https://www.angelassociation.co.nz/wp-json/wp/v2/pages/1124>
- WordPress Download Monitor records: <https://www.angelassociation.co.nz/wp-json/wp/v2/dlm_download>

The CLI combines links from the investment-publications page with Download Monitor records found by searches such as `Angel Market`, `NZGCP YCF`, and `Catalist`. Download URLs may be handler URLs like `/download/5033/` rather than stable asset filenames; callers should preserve the source page and returned title for provenance.

## Dealroom caveat

NZGCP references Dealroom as the broader startup/investor database, but the Dealroom API is commercial and out of scope for this keyless skill. This skill links public NZGCP Dealroom reports only; it does not query Dealroom.

## Error handling

All network calls use a timeout. Upstream HTTP, network, timeout, or JSON failures are reported as `upstream_unavailable` with exit code 2 for JSON commands. The smoke test treats that as a clean skip for live network checks.
