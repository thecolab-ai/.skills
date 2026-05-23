# PAK'nSAVE NZ API notes

This skill is an unofficial wrapper around the same public web APIs used by `paknsave.co.nz`.

## Source and auth

- Website: `https://www.paknsave.co.nz`
- Edge API: `https://api-prod.paknsave.co.nz/v1/edge`
- Auth model: short-lived guest bearer token from `POST /api/user/get-current-user`
- Token cache: `~/.cache/paknsave-cli/guest-token.json`
- Default store: PAK'nSAVE Papakura, `a7d09522-bee2-41e4-8fe0-0b82b7f342f5`

No username, password, Clubcard token, cookie, or private credential is required.

## Endpoint families used

- `GET /store` for stores
- `GET /store/{storeId}/categories` for category trees
- `POST /search/paginated/products` for search and specials
- `POST /store/{storeId}/decorateProducts` for exact product IDs

## Stability and safety

- Treat prices as live store-specific snapshots, not historical facts.
- Endpoint shapes can change without notice because this is not an official API.
- If a request fails, retry once with `token --refresh` or delete the token cache before assuming the product is unavailable.
- Do not perform account, checkout, or trolley actions from this skill.
- Avoid high-volume scraping; use narrow queries and small limits unless the user explicitly needs broader coverage.
