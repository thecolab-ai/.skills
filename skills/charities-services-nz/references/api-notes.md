# Charities Services OData notes

## Source

- Service root: `https://www.odata.charities.govt.nz/`
- Metadata: `https://www.odata.charities.govt.nz/$metadata`
- Format: OData v2-style service, JSON verbose when requested with `Accept: application/json`, XML service document/metadata, and documented `$format=csv` output.
- Authentication: none observed for read-only OData queries.

## Important collections

- `Organisations` - charity identity/contact/registration rows for individual organisations.
- `Groups` - group registration rows.
- `Officers` - officer rows linked to organisations.
- `Activities`, `Beneficiaries`, `Sectors`, `SourceOfFunds` - lookup/reference collections.
- `AnnualReturn` - annual-return financial and reporting fields.
- `GrpOrgLatestReturns` - denormalised group/organisation latest-return view with identity, registration, sector/activity names, and many financial fields.
- `GrpOrgAllReturns` - denormalised historical annual-return rows.
- `vOrganisations`, `vOfficerOrganisations` - views exposed by the service.

Use `python3 skills/charities-services-nz/scripts/cli.py collections --json` for the live collection list and `fields <Entity>` for live schema.

## Spot queries from investigation

Run date: 2 July 2026.

Grant-making stated purpose:

```text
Organisations?$filter=PurposeToGiveGrantsAndDonations eq true
```

CLI equivalent:

```bash
python3 skills/charities-services-nz/scripts/cli.py grant-intent --registered-only --limit 20 --json
```

Latest returns with grants paid within NZ:

```text
GrpOrgLatestReturns?$filter=GrantsPaidWithinNZ gt 0
```

CLI equivalent:

```bash
python3 skills/charities-services-nz/scripts/cli.py grants-paid --registered-only --min-amount 0 --limit 20 --json
```

Top grant-paying latest returns by amount:

```bash
python3 skills/charities-services-nz/scripts/cli.py grants-paid \
  --registered-only \
  --orderby "GrantsPaidWithinNZ desc" \
  --select "Name,CharityRegistrationNumber,RegistrationStatus,YearEnded,GrantsPaidWithinNZ,TotalGrossIncome,CharitySummaryURL" \
  --limit 20 --json
```

Targeted officers for an organisation:

```bash
python3 skills/charities-services-nz/scripts/cli.py officers 50607 --json
```

The CLI selects public officer-role fields and strips any email-like fields defensively because officer email/contact harvesting is restricted by anti-spam/privacy terms.

Latest or historical annual-return rows for an organisation/group id:

```bash
python3 skills/charities-services-nz/scripts/cli.py returns 50607 --json
python3 skills/charities-services-nz/scripts/cli.py returns 50607 --all --json
```

Activity taxonomy:

```bash
python3 skills/charities-services-nz/scripts/cli.py activities --json
```

Activity codes observed for grant-making signals include `2` (makes grants/loans to individuals) and `3` (makes grants to organisations).

## Useful fields

`Organisations`:

- `OrganisationId`
- `Name`
- `CharityRegistrationNumber`
- `RegistrationStatus`
- `NZBNNumber`
- `CompaniesOfficeNumber`
- `CharityEmailAddress`
- `WebSiteURL`
- `PostalAddressCity`, `PostalAddressSuburb`, `PostalAddressPostcode`
- `StreetAddressCity`, `StreetAddressSuburb`, `StreetAddressPostcode`
- `DateRegistered`, `DeregistrationDate`, `DeregistrationReasons`, `ModifiedOn`
- `MainActivityId`, `MainBeneficiaryId`, `MainSectorId`
- `PurposeToGiveGrantsAndDonations`
- `OrganisationGeneratesFundsGrantsDonationsToOthers`
- `OperateOverseas`, `PercentageSpentOverseas`, overseas-region booleans
- `CharitablePurpose`, `EntityStructure`, `LegalStructure`

`Officers`:

- `OfficerId`
- `OrganisationId`
- `FullName`, `FirstName`, `MiddleName`, `LastName`
- `OfficerStatus`
- `PositioninOrganisation`
- `PositionAppointmentDate`, `LastDateAsAnOfficer`
- `BodyCorporateName`, `IsaBodyCorporate`

`GrpOrgLatestReturns` / `GrpOrgAllReturns`:

- Identity: `Id`, `EntityType`, `Name`, `CharityRegistrationNumber`, `NZBNNumber`, `CharitySummaryURL`
- Registration: `RegistrationStatus`, `DateRegistered`, `DeregistrationDate`, `DeregistrationReasons`
- Classification: `MainActivityName`, `MainBeneficiaryName`, `MainSectorName`, `Activities`, `AreasOfOperation`, `Beneficiaries`, `Sectors`, `SourcesOfFunds`
- Return metadata: `AnnualReturnId`, `ReportingTier`, `YearEnded`, `FinancialPositionDate`, `ReportingCurrency`
- Grant fields: `GrantsPaidWithinNZ`, `GrantsPaidOutsideNZ`, `GrantsAndDonationsMade`, `GrantsorDonationsPaid`, `GeneralGrantsReceived`, `CapitalGrantsAndDonations`, `GrantsRevenueFromLocalOrCentralGovernment`, `GrantsRevenueFromOtherSources`
- Financial totals: `TotalGrossIncome`, `TotalExpenditure`, `TotalAssets`, `TotalLiabilities`, `TotalEquity`, `NetSurplusDeficitForTheYear`

## OData syntax examples

Name contains search:

```text
substringof('Auckland',Name) eq true
```

Registered grant-makers only:

```text
PurposeToGiveGrantsAndDonations eq true and RegistrationStatus eq 'Registered'
```

Latest returns with substantial NZ grants:

```text
GrantsPaidWithinNZ gt 100000 and RegistrationStatus eq 'Registered'
```

OData v2 responses may be either:

- `{"d": [ ... ]}` for normal collection queries, or
- `{"d": {"results": [ ... ], "__count": "..."}}` when `$inlinecount=allpages` is requested.

The CLI normalises both shapes into `rows` and strips deferred navigation properties.

## CSV fallback

Charities Services documents alternate formats with `$format=csv` and supports `$returnall=true`. The CLI uses this as a practical fallback for simple targeted `Organisations` `search` and `org` lookups when JSON OData is blocked by upstream bot protection:

```text
Organisations?$format=csv&$returnall=true
```

The fallback is intentionally not used for broad generic `query`, `officers`, or `returns` commands, where paging/filtering through JSON OData is safer and more predictable.

## Interpretation cautions

- `GrpOrgLatestReturns` means latest return in the OData view, not necessarily a recent filing. Always inspect `YearEnded` before calling data current.
- `RegistrationStatus` can be `Deregistered`; pass `--registered-only` for current charity discovery.
- Grant expenditure fields are self-reported financial-return fields. They do not prove that a charity currently accepts applications or has an open grant round.
- `PurposeToGiveGrantsAndDonations` is a declared-purpose signal; `GrantsPaidWithinNZ` is a reported-payment signal. Use both when building a high-confidence grant-maker shortlist.
- Upstream Incapsula/bot protection can block some requests. Treat `blocked_by_upstream` as a source availability problem; do not fabricate rows.
- Keep queries narrow; do not mirror the whole service.
