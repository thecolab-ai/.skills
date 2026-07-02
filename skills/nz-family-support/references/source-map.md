# Official source map and safety notes

This skill intentionally maps questions to official sources only. It must not become a
calculator, eligibility engine, application helper, or private-data collection flow.

## Safety boundary

- Do not ask for or process exact income, rent, address, IRD number, client number,
  custody details, bank details, identity documents, or application evidence.
- Do not infer eligibility or amounts from chat content.
- Do not submit forms, log in, create accounts, upload documents, or contact agencies.
- Use the wording "may be relevant" / "check the official page" rather than "you qualify".
- For personal circumstances, send users to an official checker or the relevant agency page.

## Official sources included

| Source ID | Official source | Use for |
| --- | --- | --- |
| `ird-support-for-families` | <https://www.ird.govt.nz/support-for-families> | IRD family-support landing page and programme discovery. |
| `ird-working-for-families` | <https://www.ird.govt.nz/working-for-families> | Working for Families Tax Credits and IRD WFF rules. |
| `ird-wff-msd-handoff` | <https://www.ird.govt.nz/working-for-families/all-about-working-for-families/msd> | Deciding whether IRD or MSD/WINZ is the right route for WFF where benefits/MSD assistance are involved. |
| `ird-best-start` | <https://www.ird.govt.nz/working-for-families/types/best-start> | Best Start tax credit questions for new babies/young children. |
| `ird-familyboost` | <https://www.ird.govt.nz/familyboost> | IRD FamilyBoost childcare payment for early childhood education fees. |
| `msd-checker` | <https://check.msd.govt.nz/> | Official private MSD "what you might get" pre-check across support types. |
| `msd-accommodation-supplement-checker` | <https://check.msd.govt.nz/services/accommodation-supplement> | Official private pre-check for Accommodation Supplement. |
| `winz-accommodation-supplement` | <https://www.workandincome.govt.nz/products/a-z-benefits/accommodation-supplement.html> | Accommodation Supplement rules and application pathway. |
| `winz-childcare-subsidy` | <https://www.workandincome.govt.nz/products/a-z-benefits/childcare-subsidy.html> | MSD/WINZ Childcare Subsidy rules and application pathway. |
| `winz-working-for-families` | <https://www.workandincome.govt.nz/products/a-z-benefits/working-for-families.html> | WINZ-facing Working for Families information. |

## Routing patterns

- **Starting point:** use `ird-support-for-families`, `msd-checker`, and `ird-working-for-families`.
- **Working for Families:** use `ird-working-for-families`; add `ird-wff-msd-handoff` and
  `winz-working-for-families` if MSD/WINZ or benefits are mentioned.
- **New baby / Best Start:** use `ird-best-start` and the IRD WFF pages.
- **Childcare:** compare `ird-familyboost` and `winz-childcare-subsidy`; they are different programmes.
- **Housing costs:** use the MSD Accommodation Supplement checker and the WINZ Accommodation Supplement page.
- **On a benefit / dealing with WINZ:** check `ird-wff-msd-handoff` before naming the agency route.

## Example safe language

> These official pages may be relevant. I cannot calculate or decide entitlement here. For
> personal circumstances, use the linked official checker or contact IRD/MSD/WINZ directly.

## Example unsafe language to avoid

> Based on your rent and income, you qualify for $X per week.

> Give me your address, income, and IRD number and I will work out your payment.
