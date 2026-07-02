# Class 4 grants / Granted.govt.nz source notes

## Primary sources

- Granted portal: <https://www.granted.govt.nz/>
- DIA source page: <https://www.dia.govt.nz/Gambling-statistics-class-4-grants-data>
- data.govt.nz package: `class-4-grants-data` / "Grants from Gaming Machine Profits"
- Grants CSV resource: `06d99ad0-47d6-4591-84c7-8872a4f77da9`
- Related data.govt.nz package: `class-4-gambling-venue-and-gaming-machine-numbers-quarterly-lists`
- DIA Class 4 society website list: <https://www.dia.govt.nz/Services-Casino-and-Non-Casino-Gaming-List-of-Society-Websites>

## Grants CSV fields observed

The CLI streams the public CSV directly and does not cache or mutate it. Fields observed in the current resource:

- `Society_Name` - Class 4 society/funder
- `Organisation_Name` - recipient name as supplied
- `Final_Organisation_Name` - normalised recipient name used for aggregation
- `NZBN`
- `Status` - accepted or declined application status
- `Amount_Requested_Final`
- `Amount_Granted_Final`
- `Date_of_Accept/Decline`
- `Year_of_Accept/Decline`
- `Category_1`
- `Category_2`
- `Date_of_Refund`
- `Is_Refund`
- `Amount_Refunded_Clean`
- `Territorial_Local_Authority`
- `Region`

Amounts are supplied as dollar-formatted strings in the source CSV. The CLI adds numeric `*_Number` fields in JSON row output and uses parsed numeric values for totals and aggregations.

## Caveats

- The grants CSV is large (around tens of MB). Aggregate commands stream the file and may take several seconds.
- Venue and gaming-machine quarterly lists are currently XLSX resources. This skill exposes discovery/source links for those files but does not parse XLSX because repository conventions prefer Python standard library only.
- Granted.govt.nz is treated as a public read-only portal. The CLI uses the underlying DIA/data.govt.nz public resources rather than browser automation.
- The DIA society website command extracts public links from an HTML page and is intended for discovery, not as a canonical register of current licence status.
