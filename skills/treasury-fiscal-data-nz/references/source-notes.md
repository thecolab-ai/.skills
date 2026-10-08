# Source notes

- Owner/source: New Zealand Treasury budget and forecast publications
- Primary source: https://www.treasury.govt.nz/publications/budgets/forecasts
- Authentication: none
- Last verified: 2026-10-08
- Current parsed publications: BEFU 2026 charts/data and 2026/27 Estimates expenditure workbooks
- Access: public and read-only; CC BY 4.0; hosts `treasury.govt.nz`, `www.treasury.govt.nz`

`latest` is restricted to primary Budget, Half Year and Pre-election Economic and Fiscal Update
releases and excludes supplementary publications, site navigation and self-links. `sources` groups
official XLS/XLSX/CSV/PDF resources beneath those releases.

Forecast values come from the latest primary EFU release's explicitly titled key-indicator summary (Table 1 in BEFU/HYEFU, Table 2 in PREFU 2026).
Appropriation and Vote values come from the expenditure workbook's `Raw Data` sheet. Each output
record represents one published amount and retains its unit, year-ending-30-June period, published
amount type (`Actuals`, `Estimated Actual`, or `Main Estimates`), publication, workbook, worksheet,
one-based row and exact cell. Vote lookup accepts both the source name (`Health`) and its conventional
form (`Vote Health`).

`compare` resolves both requested vintages to primary EFU releases, excluding supplementary pages and
fiscal models. It selects the unique Charts and Data workbook and compares only the exact shared
key-indicator definition, unit, year-ending-30-June basis and forecast period. Each side retains publication,
workbook, sheet, row, column and cell provenance. The emitted delta uses the published unit. Arbitrary,
missing or ambiguous vintages, changed definitions and publications without shared forecast periods
return exit 7 rather than a guessed comparison. Fiscal data retrieval is not financial or investment advice.

PREFU 2026 uses text years and numeric strings, parenthesised negatives, split unit labels and footnoted statuses. The parser requires one explicitly titled summary, unique years and recognised units/status notes. The 2026 footnote marks fiscal values, unemployment and CPI as actuals; GDP and the current account remain forecasts. Wrong or ambiguous tables and unknown footnotes fail closed.
