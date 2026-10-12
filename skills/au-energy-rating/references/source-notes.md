# Source notes

- Primary owner: Australian Government Department of Climate Change, Energy, the Environment and Water
- Primary source: https://data.gov.au/data/api/3/action/package_show?id=559708e5-480e-4f94-8429-c49571e82761
- Package id: `559708e5-480e-4f94-8429-c49571e82761`
- Package name: `energy-rating-for-household-appliances`
- Data licence: stated on the package. On 2026-10-12 the package `license_title` was Creative Commons Attribution 3.0 Australia, `license_id` was `cc-by`, and `license_url` was the package's `http://creativecommons.org/licenses/by/3.0/au/`. The CLI copies those fields. It does not fetch the licence host.
- Declared outbound hosts: data.gov.au
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-12

The package notes say the datasets describe energy efficiency of labelled
products and that suppliers register appliances to be sold in Australia and
New Zealand. The notes list air conditioners, clothes dryers, dishwashers,
clothes washers, fridges and freezers, televisions, computer monitors and
swimming pool pumps. The same package also has datastore resources for LED
lamps and commercial ice-makers.

## What the CLI requests

- `package_show` for the fixed package id above.
- `datastore_search` with `resource_id` and `limit` only, and only after that
  id is listed on this package with `datastore_active: true`.

No caller-supplied URL is accepted. HTTPS requests and redirects must stay on
`data.gov.au` port 443. Environment proxies are not used. The client sends
`User-Agent: thecolab-au-energy-rating/1.0` and `Accept: application/json`,
with a 15 second timeout and a 524288 byte response cap. At most 3 redirects
are followed. HTTP 429 and 503 are errors. A non-JSON or truncated body is an
error. Responses over the byte cap are not parsed.

CSV resources are several megabytes. Dictionary resources are DOCX files and
are not datastore-active. Neither kind of file is downloaded. `preview` is a
bounded sample, not an export: limit is at most 20 and there is no offset.

## Fields, units and freshness

Datastore records are passed through with the source field names. Do not
rename them or coerce `N/A` to null. Null stays null. Star-rating fields such
as `c_star_mixed` are source strings, not a converted numeric scale. Power and
capacity fields keep the units implied by their source names; this skill does
not convert them.

`metadata_modified` and resource `last_modified` are copied as published.
They have no timezone suffix. They are source update timestamps, not the
retrieval time. `retrieved_at` is when this client received the response, in
UTC with a trailing `Z`.

Resource titles on several tables are padded with spaces and may end with a
filename token. The CLI collapses space and tab runs to a single space and
strips the ends. It does not drop the remaining tokens.

An empty datastore (`total` 0 and `records` `[]`) is a successful empty
preview. `success: false`, malformed JSON, or a total that disagrees with the
record list is a schema failure and yields no invented rows.
