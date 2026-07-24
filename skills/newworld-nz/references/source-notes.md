# Source notes

- Primary owner: Foodstuffs New Zealand
- Primary source: https://www.newworld.co.nz
- Declared outbound hosts: api-prod.clubplus.co.nz,api-prod.newworld.co.nz,login.clubplus.co.nz,www.newworld.co.nz
- Access mode: authenticated-personal
- Authentication: mixed
- Last verified: 2026-07-24

Public catalogue requests use a guest bearer; orders, purchases, list reads, and cart reads require user-authorised Club+ credentials and return personal data. Explicit commands can select an account store, create, rename, delete, or change products in the account holder's own lists, and add, update, or remove products in their cart. Passwords remain environment-only, while rotating tokens are stored in a private local cache. List deletion and list/cart product removal require `--yes`. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.
