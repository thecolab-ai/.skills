# Work and Income rates and A-Z benefit source notes

## Public sources used

This skill uses public Work and Income New Zealand website pages only:

- Annual benefit/payment rates: `https://www.workandincome.govt.nz/products/benefit-rates/benefit-rates-april-<year>.html`
- A-Z benefit index: `https://www.workandincome.govt.nz/products/a-z-benefits/`
- A-Z benefit detail pages: `https://www.workandincome.govt.nz/products/a-z-benefits/<slug>.html`

The implementation parses structured public HTML:

- rate pages are organised as accordion sections (`wi-accordion--section`) with `h2` payment names and embedded HTML tables;
- A-Z index entries use `div.links.default` blocks with a link and summary paragraph;
- A-Z detail pages are parsed from public `main` content, `h1`, `h2` sections, and regular links.

## API status

No open public MSD/WINZ rates API was found for these current payment-rate and entitlement pages. The MSD API developer portal (`api.msd.govt.nz`) is partner-gated and not used by this skill.

## Access and blocking notes

Work and Income pages may be protected by Incapsula or similar bot/data-centre filtering. Some cloud or CI environments can receive HTTP 403 or related challenge pages even though the public site is reachable from normal browsers.

The CLI treats HTTP 403/429, Incapsula-like responses, network failures, and timeouts as upstream availability/blocking errors. The smoke test skips cleanly in those cases rather than failing due to an upstream anti-bot block.

## Safety and scope

- Read-only public website access only.
- No login, MyMSD access, application submission, or form mutation.
- No private user information is collected.
- The skill extracts official text and tables, but does not calculate or decide entitlement eligibility.
- Users should cite and defer to the returned Work and Income `source_url` for authoritative decisions.
