# Stats NZ API Notes

## Implemented public sources

- Stats NZ large-datasets CSV catalogue: `https://www.stats.govt.nz/large-datasets/csv-files-for-download/`
- Estimated population indicator: `https://www.stats.govt.nz/indicators/population-of-nz/`
- Stats NZ regional place summaries: `https://tools.summaries.stats.govt.nz/places/RC/<region-slug>`
- National population projections release: `https://www.stats.govt.nz/information-releases/national-population-projections-2024base2078/`

The CLI is read-only and does not write cache files. It fetches live pages or CSVs for each command.

## Dataset discovery

The large-datasets catalogue embeds JSON in `pageViewData`. The CLI reads `PageBlocks[].BlockDocuments[]` and discovers current release CSV URLs by title:

- CPI: title contains `Consumers price index` and `index numbers`
- GDP: title contains `Gross domestic product`
- Migration: title contains `International migration` and `estimated migration by age and sex`

The release-specific CSV paths change when Stats NZ publishes a new release, so commands do not hard-code current file URLs.

## Wired series

- `CPIQ.SE9A` - Consumers price index, all groups, New Zealand, quarterly index
- `SNEQ.SG01RSC00B01` - GDP production measure, chain-volume, seasonally adjusted, total
- `SNEQ.SG01RSC01B01PC` - GDP production measure, quarterly percentage change
- `SNEQ.SG01RSC01B01AC` - GDP production measure, same-quarter previous-year percentage change
- `SNEQ.SG02RSC00B15` - GDP expenditure measure, chain-volume, seasonally adjusted, total
- `SNEQ.SG02RSC31B15PC` - GDP expenditure measure, quarterly percentage change

`series <id>` scans the wired CPI and GDP CSV releases for exact `Series_reference` matches.

## Command notes

- `cpi` reports the latest all-groups CPI index and computes quarterly and annual percentage change from the same series.
- `population` without flags reads the Stats NZ population indicator. `--projection YEAR` reads the national population projections graph CSV. `--region REGION` reads the regional council place summary and extracts the latest estimated resident population.
- `migration` filters the migration age/sex CSV to long-term migrant totals by month, sex `TOTAL`, age `TOTAL`, and computes net migration as arrivals minus departures.
- `gdp` reports the latest wired production and expenditure headline series from the quarterly GDP CSV.
- `search` searches public CSV catalogue titles and returns source URLs.

## Refresh cadence

- CPI: quarterly
- GDP: quarterly
- International migration: monthly
- National estimated population: quarterly
- Regional estimated resident population: annual
- National population projections: periodic release, not every quarter

## Auth and omitted surfaces

Implemented sources need no API key, username, password, cookies, or browser session.

The modern Stats NZ OData/API and Administrative Data Explorer surfaces were not shipped because public discovery indicated subscription-key or registration requirements. Geographic data from Datafinder is also not shipped because this lightweight CLI focuses on official statistics and CSV/time-series workflows rather than GIS extraction.
