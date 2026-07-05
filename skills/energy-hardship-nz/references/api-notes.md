# Energy Hardship NZ Source Notes

## MBIE energy-hardship measures

Primary page:
`https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-statistics-and-modelling/energy-publications-and-technical-papers/reporting-on-energy-hardship-measures`

The current page identifies the December 2025 release covering the year ended
June 2024. It links a PDF report and an XLSX workbook:

- Report PDF: `https://www.mbie.govt.nz/dmsdocument/31651-report-on-energy-hardship-measures-year-ended-june-2024`
- Workbook XLSX: `https://www.mbie.govt.nz/dmsdocument/31652-energy-hardship-measures-year-ended-june-2024`
- Earlier PDF: `https://www.mbie.govt.nz/dmsdocument/31653-report-on-energy-hardship-measures-year-ended-june-2022`

In automated Python/curl contexts MBIE can return a 403 from the page and
document URLs. The CLI treats this as a source access block, not a parser crash.
The `measures --year-ended 2024` command includes the five national summary
values from the PDF report key insights, but leaves confidence intervals null
because the report summary does not show them and the workbook is not fetched or
parsed when direct access is blocked.

## Stats NZ Household Expenditure Statistics

Primary page:
`https://www.stats.govt.nz/information-releases/household-expenditure-statistics-year-ended-june-2023/`

The page embeds release document metadata in `pageViewData`. The useful files
are:

- Household expenditure statistics CSV ZIP
- Household expenditure statistics XLSX
- Detailed household expenditure CSV ZIP

The standard CSV ZIP contains `exp-t1to4-datafile_2023.csv` and
`exp-csv-codes.xlsx`. The CLI parses the CSV and reads the `NZHEC` sheet from the
small XLSX codebook with a minimal stdlib XML reader. It does not implement a
general Excel calculation engine, chart reader, pivot-table parser, or formula
evaluator.

The feasible public CSV output for this skill is national average weekly
household expenditure for HEC codes under `04.5`:

- `04.5`: electricity, gas, and other domestic fuels
- `04.5.01`: electricity
- `04.5.02`: reticulated gas
- `04.5.03`: solid fuels
- `04.5.04`: liquid fuels
- `04.5.05`: other domestic fuel and service fees

The public CSV does not include the income-decile or income-quintile domestic
energy burden ratios requested by the issue. The CLI therefore reports a
`partial` result for `burden`, with a clear blocked reason for the income burden
component. Its expenditure share is a derived share of the published national
top-level expenditure groups, not an income burden or official 10 percent/2M
measure.

## Electricity Authority disconnections

Dashboard page:
`https://www.ea.govt.nz/data-and-insights/charts-and-dashboards/disconnections-for-non-payment/`

Dataset access notes:
`https://www.ea.govt.nz/data-and-insights/how-to-access-our-downloadable-datasets/`

The dashboard page embeds a Sigma Computing iframe. The Electricity Authority
also documents public Azure Blob access at
`https://emidatasets.blob.core.windows.net/publicdata?restype=container&comp=list`.
The relevant prefix currently discoverable by the CLI is
`Datasets/Retail/Disconnections/`; at implementation time it exposed PDF source
material rather than a CSV/JSON feed. The CLI returns dashboard and blob-source
metadata, not prepay/postpay counts.

## Survey caveats

MBIE and HES figures are survey estimates, not administrative counts. Treat
confidence intervals, relative standard errors, flags, and sample-size warnings
as part of the result. Do not compare small year-on-year changes as real-world
movement unless the source marks the change as statistically significant.

Domestic energy expenditure excludes transport fuel. The MBIE five-measure suite
uses material-wellbeing questions from HES and focuses on subjective lived
experience measures, while the HES expenditure tables capture spend categories.
These are related but not interchangeable.
