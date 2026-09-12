# Source notes

## Implemented source

- Publisher: Stats NZ
- Product: **2018 Census totals by topic – national highlights**
- Product page: https://www.stats.govt.nz/information-releases/2018-census-totals-by-topic-national-highlights-updated/
- Primary source: https://www.stats.govt.nz/assets/Uploads/2018-Census-totals-by-topic-national-highlights-csv-update-30-04-20.zip
- Allowed outbound host: www.stats.govt.nz
- Format: one official ZIP containing topic CSV files
- Geography: New Zealand national total only
- Census year: 2018
- Authentication: none
- Last verified: 2026-09-12
- Access: public HTTPS download, no login or API key
- Licence: Stats NZ material is licensed under Creative Commons Attribution 4.0 unless otherwise stated on the source

The CLI uses the updated CSV archive linked from the official product page. It downloads at most 2 MiB, accepts at most 100 safe ZIP members, caps expanded content at 10 MiB, rejects path traversal and excessive expansion, and returns at most 100 observations. The live archive observed on 12 September 2026 was 71,095 bytes and contained 57 topic CSVs. Members are decoded strictly as UTF-8 first and Windows-1252 second because two published tables use Windows-1252 punctuation; undecodable bytes fail as a source-schema error rather than being replaced.

## Observation shape

Each source CSV has a category code, a labelled category dimension, and one or more published measure columns. The CLI emits one observation per category/measure cell and keeps these fields distinct. It also retains the source member and one-based CSV row number.

Known source markers are represented as `value: null`, with the exact token in `source_symbol`:

| Source token | `value_status` |
|---|---|
| blank | `missing` |
| `C`, `..C` | `confidentialised` |
| `S` | `suppressed` |
| `..`, `...` | `not_available` |
| `-` | `not_applicable` |
| `P` | `provisional_symbol` |
| `R` | `revised_symbol` |
| any other non-number | `non_numeric_source_symbol` |

The parser does not guess what unknown symbols mean. A published numeric zero remains an observed zero.

## Scope boundaries

This skill contains only documentation, fixtures, and a bounded client for the official public download. It does not claim that 2018 national highlights are a complete Census dataset. It does not claim 2023 observations, and it must not be used to infer suppressed values or combine incompatible tables.
