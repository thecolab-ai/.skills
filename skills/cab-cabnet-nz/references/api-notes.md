# CAB CABNET NZ API Notes

## Public sources checked

- `https://www.cab.org.nz/assets/data/categories.json` is a public JSON file
  for CAB website advice categories and tags. It contains article/category
  counts, not CABNET client enquiry counts.
- `https://www.cab.org.nz/api/v1/search?q=<query>` is a keyless public search
  endpoint for CAB website pages, news, advice articles, and community directory
  entries. It is useful for discovering spotlight reports and public statements.
- `https://www.cab.org.nz/api/v1/reporting` and
  `https://www.cab.org.nz/api/v1/interview/search` return `{"error":"Forbidden"}`
  without a logged-in CAB session. They appear to be CABNET/reporting surfaces,
  but are not public data exports.
- data.govt.nz searches for CABNET/client-enquiry datasets did not reveal a
  public CAB enquiry-statistics package during implementation.

## Format caveats

- CAB spotlight reports publish useful client-enquiry findings in web pages and
  PDFs, but the national aggregate enquiry tables are not available as a public
  CSV/JSON/XLSX export from the checked sources.
- Some report figures are charts in PDFs. Python stdlib does not provide a
  robust PDF table extractor, so the skill reports these as partial, report-
  backed trend evidence rather than exact numeric time series.
- The `categories` command deliberately names its source
  `cab-public-website-categories` to avoid implying that the website advice
  taxonomy is the internal CABNET enquiry taxonomy.

## Current blocked state

As of the implementation check on 2026-07-05, a keyless user can discover public
CAB pages and category metadata, but cannot retrieve structured aggregated
CABNET client-enquiry counts by year/category. The `enquiries` command returns
`structured_export_unavailable` with exit code 2 so callers can distinguish this
from a successful empty result.
