# Charities Services OData notes

## Source

- Service root: `https://www.odata.charities.govt.nz/`
- Metadata: `https://www.odata.charities.govt.nz/$metadata`
- Format: OData v2-style service, JSON verbose when requested with `Accept: application/json`, XML service document/metadata.
- Authentication: none observed for read-only OData queries.

## Important collections

- `Organisations` - charity identity/contact/registration rows for individual organisations.
- `Groups` - group registration rows.
- `Officers` - officer rows linked to organisations.
- `Activities`, `Beneficiaries`, `Sectors`, `SourceOfFunds` - lookup/reference collections.
- `AnnualReturn` - annual-return financial and reporting fields.
- `GrpOrgLatestReturns` - denormalised group/organisation latest-return view with identity, registration, sector/activity names, and many financial fields.
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

`GrpOrgLatestReturns`:

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

## Interpretation cautions

- `GrpOrgLatestReturns` means latest return in the OData view, not necessarily a recent filing. Always inspect `YearEnded` before calling data current.
- `RegistrationStatus` can be `Deregistered`; pass `--registered-only` for current charity discovery.
- Grant expenditure fields are self-reported financial-return fields. They do not prove that a charity currently accepts applications or has an open grant round.
- `PurposeToGiveGrantsAndDonations` is a declared-purpose signal; `GrantsPaidWithinNZ` is a reported-payment signal. Use both when building a high-confidence grant-maker shortlist.
- Keep queries narrow; do not mirror the whole service.
