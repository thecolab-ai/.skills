# Charities Register NZ API notes

Source: Charities Services / Ngā Ratonga Kaupapa Atawhai public OData endpoint.

- Service root: `https://www.odata.charities.govt.nz/`
- Metadata: `https://www.odata.charities.govt.nz/$metadata`
- data.govt.nz dataset: `charities-register-open-data`
- Public catalogue CSV mirror example: `https://www.odata.charities.govt.nz/Organisations?$format=csv&$returnall=true`

## Collections used

- `Organisations` - registered and previously registered charities, keyed by `OrganisationId`, with CC registration numbers in `CharityRegistrationNumber`.
- `Officers` - public officer rows linked by `OrganisationId`. The skill strips any email-like fields before output.
- `Activities` - activity taxonomy (`ActivityId`, `Name`).
- `AnnualReturn` - raw annual return rows keyed by `AnnualReturnId` and linked by `OrganisationId`.
- `GrpOrgLatestReturns` - flattened latest annual-return/financial row for organisations and groups.
- `GrpOrgAllReturns` - flattened historical annual-return/financial rows for organisations and groups.

## Query patterns

The endpoint responds to OData query parameters such as `$select`, `$filter`, `$orderby`, `$top`, and `$skip`. JSON responses are currently OData verbose-style with rows in `d.results`, so the CLI intentionally handles v1/v2-style JSON despite issue wording referring to OData v4.

Examples:

```text
Organisations?$filter=substringof('foundation',Name) eq true&$select=OrganisationId,Name,CharityRegistrationNumber
Organisations?$filter=CharityRegistrationNumber eq 'CC48800'
Officers?$filter=OrganisationId eq 260723
GrpOrgLatestReturns?$filter=Id eq 260723
GrpOrgAllReturns?$filter=Id eq 260723&$orderby=YearEnded desc
GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ ge 10000&$orderby=GrantsPaidWithinNZ desc
Activities?$select=ActivityId,Name&$orderby=Name
```

## Caveats

- `$top` is capped at 1000 by the skill. Use `--skip` for targeted pagination.
- `$returnall=true` appears in the public CSV mirror and is documented here for fallback use; avoid using it for unrestricted bulk extraction in normal agent workflows.
- Incapsula/bot protection can return HTTP 403 from some hosts. The CLI reports `blocked_by_upstream` and tries the public `Organisations` CSV mirror for `search` and `org` before failing.
- Financial grant fields are annual-return facts, not an assertion that a charity currently accepts applications. Always check `YearEnded`, registration status, and the charity's own website.
