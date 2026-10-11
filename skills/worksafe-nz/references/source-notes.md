# WorkSafe public exports

- Authentication: none
- Last verified: 2026-10-08

Keyless first-party public downloads. Discovery reads
`data-props` JSON on the following Data Centre summary pages, using
`datasetDownload.path` rather than relying on permanent S3 object names:

| Dataset selector | Landing page |
|---|---|
| `incidents` | https://data.worksafe.govt.nz/graph/summary/incidents |
| `concerns` | https://data.worksafe.govt.nz/graph/summary/concerns |
| `injuries_serious_harm` | https://data.worksafe.govt.nz/graph/summary/injuries_serious_harm |
| `serious_harm` | Same injury page, `supplementaryDownloadFiles`, “Download Serious Harm - HSE” |
| `fatalities` | https://data.worksafe.govt.nz/graph/summary/fatalities |

Current downloads (the CLI discovers replacements when its page cache expires):

- Incidents: https://data-centre-public.s3.ap-southeast-2.amazonaws.com/data-sets/incidents/xJ9mVTCxmyW3yQ30kgOQxm1Fbs6irgE8INQAnFym.csv
- Concerns: https://data-centre-public.s3.ap-southeast-2.amazonaws.com/data-sets/concerns/8iupxnNoWaFkREYuyvQt3nwT6JaYTFXM6OAP6Hjx.csv
- HSWA injury/illness: https://data-centre-public.s3.ap-southeast-2.amazonaws.com/data-sets/injuries_serious_harm/3ioRr4EA4UjhH9ekeqMlAMHr2bjeKqKpuB3JaEbR.csv
- HSE serious harm: https://data-centre-public.s3.ap-southeast-2.amazonaws.com/RTDCv2YRVwcRidEcEihb4gMCqoaVq0gZcWfvqY37.csv
- Fatalities: https://data-centre-public.s3.ap-southeast-2.amazonaws.com/data-sets/fatalities/DjRBZ4gT3OWgjt2DJgvdNpuak8IdS1LWxVbL4BGL.csv

## Schema and provenance

Notifications have Year, Month, Month_Year, Notification_Type, AFF2017,
AFF2017_Lvl2, IndustryLvl1–4, Local_Government_Region, Region, Investigated,
Notice_Warning_or_Agreement, HSWA_Classification and integer Count. Legacy HSE
uses IndustryLVL2–4 and lacks HSWA_Classification. Summaries **sum Count**, not
CSV rows. Blank or malformed counts fail; they are never silently discarded.

The fatalities CSV has FatalID and no Count, uses lower-case
local_government_region, and includes personal attributes. The parser counts
one row per unique FatalID; command output aggregates by year, industry and
region, excluding IDs and personal attributes. It includes the whole-system
series, not just rows marked WorkSafe_Confirmed_Fatalities.

`latest_data` is the greatest Year/Month stated in the downloaded CSV, across
the full dataset before filtering. `first_data` is the earliest CSV month;
`page_updated` preserves the landing page's lastUpdated value. These are
separate facts: on verification the fatality page was updated 03 Sep 2026,
its CSV extended to 2025-12, and dashboard labels described data to Aug 2025.
The other current CSVs extended to 2026-10 and their pages were updated
06 Oct 2026. Do not reinterpret latest_data as a completed reporting period.

Cached results retain the actual download timestamp. Source discovery uses
page retrieval timestamps; data records use CSV retrieval timestamps.
`sources` sets `latest_data` to the page update date (also `page_updated`);
`datasets` and data queries use the latest CSV month instead. Discovery does not
claim to know CSV coverage without reading the export. Mixed download provenance is carried on each sources or
datasets record as well as the enclosing envelope. A discovery/cache problem
fails explicitly; there is no silent stale-file fallback.

## Reuse and limits

The Data Centre requests WorkSafe credit but states no specific data licence.
Output `licence` describes that request; it does not assert CC licensing.
[WorkSafe copyright terms](https://www.worksafe.govt.nz/about-us/about-this-site/copyright/)
permit accurate reproduction with source/copyright acknowledgement except
third-party material, and prohibit misleading or derogatory use. Their
application to each S3 export is not explicitly stated; verify before
redistribution. The code's MIT licence does not license the datasets.

Data Centre robots.txt permits all paths. WorkSafe's main site excludes admin,
security, error and search paths; this skill uses none of those. S3 robots.txt
returned AccessDenied (403); only explicitly published CSV objects are read,
without bucket listing or crawling.

Notification dates reflect reporting, not necessarily occurrence. Data quality
and industry assignments can change. The November 2022 case-management change
excluded section 199 notifications and changed incident-type consistency.
Investigated and Notice_Warning_or_Agreement are under development; do not treat
blank fields as “No”. HSE serious-harm definitions differ from HSWA injury and
illness; analyse each dataset separately rather than adding them together. The
historical export is described as January 2010–March 2016 but its notification
months extend to July 2019. Late HSE notifications can concern events before
4 April 2016, so do not interpret that coverage as newer HSE events.

Fatalities include WorkSafe register and accepted ACC fatal claims (including
other regulators' jurisdictions). WorkSafe recommends a three-month lag for
stability; historical records can be revised. Deaths from occupational disease
are not in this acute fatality series. Counts are not incidence rates and do
not supply a workforce denominator. Construction and waste-sector filters are
W1 safety context, not demolition material flows, hazards at a specific site,
or an inventory of near misses. No geometry is available.
