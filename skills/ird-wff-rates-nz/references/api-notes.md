# IRD WFF / FamilyBoost source notes

## Scope

This skill covers public Inland Revenue rate/threshold/eligibility parameters needed for Working for Families entitlement pre-checks:

- Family Tax Credit
- In-Work Tax Credit
- Best Start Tax Credit
- Minimum Family Tax Credit
- Working for Families abatement threshold and abatement rate
- FamilyBoost reimbursement rates, quarterly income caps, and eligibility criteria

It deliberately does **not** cover aggregate WFF statistics; those are CKAN/data.govt.nz catalogue datasets and belong in `data-govt-nz`.

## Official public sources

| Topic | Source |
| --- | --- |
| WFF overview | <https://www.ird.govt.nz/working-for-families> |
| Family Tax Credit | <https://www.ird.govt.nz/working-for-families/types/family-tax-credit> |
| In-Work Tax Credit | <https://www.ird.govt.nz/working-for-families/types/in-work-tax-credit> |
| Best Start | <https://www.ird.govt.nz/working-for-families/types/best-start> |
| Minimum Family Tax Credit | <https://www.ird.govt.nz/working-for-families/types/minimum-family-tax-credit> |
| FamilyBoost amount rules | <https://www.ird.govt.nz/familyboost/how-much-familyboost-can-you-claim> |
| FamilyBoost eligibility | <https://www.ird.govt.nz/familyboost/can-you-get-familyboost> |

## Data model notes

- `tax_year` is the year ending 31 March. Example: tax year `2027` covers 1 April 2026 to 31 March 2027.
- Amount fields are NZ dollars unless the field name says `rate`.
- Weekly values reflect IRD's published weekly examples/tables. Annual values may be source-published or weekly amounts multiplied/rounded as IRD presents them.
- WFF abatement is modelled separately from each credit because the abatement can flow from Family Tax Credit to In-Work Tax Credit.
- Best Start has its own threshold and abatement rate.
- FamilyBoost is quarterly, not annual, and applies to eligible ECE fees after excluding donations/subsidies such as MSD Childcare Subsidy.

## Fetching behaviour

IRD pages are public HTML, not a stable machine-readable API. Direct HTTP can work from some networks and be blocked from others. The CLI therefore:

1. Keeps source-cited built-in schedules for deterministic `rates`, `thresholds`, `credit get`, and `familyboost` output.
2. Offers `--probe` to perform a short, read-only fetch of cited IRD pages and report availability/last-updated snippets.
3. Treats HTTP errors, bot challenges, and timeouts as upstream unavailability. It does not try to bypass controls.

## Maintenance checklist

Re-check this skill after Budget announcements, 1 April annual updates, or IRD FamilyBoost policy changes:

- Family Tax Credit eldest/other-child annual and weekly amounts.
- In-Work Tax Credit first-three-child amount, extra-child amount, and temporary-policy notes.
- WFF abatement threshold and rate.
- Best Start weekly/annual amount, threshold, abatement rate, and birth-date transition rules.
- Minimum Family Tax Credit annual/weekly after-tax income floor.
- FamilyBoost reimbursement percentage, maximum quarterly payment, full-rate threshold, income cap, and abatement rate.
