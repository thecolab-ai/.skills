# Source notes

- Primary owner: Woolworths New Zealand
- Primary source: https://www.woolworths.co.nz
- Declared outbound hosts: auth.woolworths.co.nz,iam.woolworths.co.nz,www.woolworths.co.nz
- Access mode: authenticated-personal
- Authentication: mixed
- Last verified: 2026-07-24

Public product requests require no account. Orders, favourites, saved lists, and trolley reads require user-authorised Woolworths credentials and return personal data. Tax-invoice enrichment combines a user-provided local PDF with the matching past-order items response, retaining invoice quantities/prices while adding confidence-scored catalogue SKUs. Explicit commands can create/delete saved lists, add/update/remove saved-list products, and add/update/remove/clear trolley products. The site's supported empty-list path saves the current trolley, so the CLI verifies that the trolley is empty before using it. Passwords remain environment-only; browser session cookies are stored in a private, account-bound cache and refreshed only from Woolworths-domain responses. Destructive removals require `--yes`, and checkout/order placement is not exposed. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.
