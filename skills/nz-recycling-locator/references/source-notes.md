# Source notes and output semantics

- Authentication: none
- Last verified: 2026-10-08

Verified on 8 October 2026 using live public HTTP responses. Directory counts
are observations, not hard-coded CLI assertions. All sources are keyless and
read-only. Unknown dataset licences are omitted; public access does not imply
an open reuse licence. `SKILL.md`'s MIT licence covers the skill code only.

| Source selector | Publisher / direct endpoint | Verified response | Limits |
|---|---|---|---|
| `recyclemap` | RecycleMap NZ: `https://www.recyclemap.co.nz/wp-json/wpgmza/v1/markers`, `/maps`, `/categories` | 4,001 markers; 22 maps | Volunteer listings, no per-record date or verified dataset licence |
| `wasteminz` | WasteMINZ: `https://www.google.com/maps/d/kml?mid=1ncyWOEWbXMSiycgz48swYqMj4aHJnSE&forcekml=1` | 249 point placemarks | Names, WGS84 coordinates and acceptance descriptions; no street-address/hours fields in the tested placemarks |
| `branz` | BRANZ: `https://services7.arcgis.com/vkPf8weODt71Prmb/arcgis/rest/services/Waste_Map_Facility_Locations/FeatureServer/0` | 503 facilities after excluding five Planned entries (508 upstream) | C&D/material flags, address, region, facility type; last data edit 2025-11-24T00:48:12.874Z |
| `ecycle` | E-Cycle: `https://www.e-cycle.co.nz/wp-admin/admin-ajax.php?action=store_search&lat=-36.8485&lng=174.7633&max_results=1000&search_radius=5000&autoload=1` | 17 nationwide partners | Without `autoload=1`, the same request returned only one site; acceptance varies and charges may apply |
| `agrecovery` | Agrecovery: `https://agrecovery.co.nz/wp-json/wp/v2/ag_site?per_page=100&page=1&acf_format=standard&_fields=id,title,acf&orderby=title&order=asc` | 241 active sites across three pages | Programme-specific agricultural packaging; raw scheme labels retained rather than general plastic acceptance |
| `beautification` | Beautification Trust: `https://api.mapme.com/api/stories/aggregated/af29690b-4cd0-484f-a211-8f3e12fa51b4` | 144 sections, 140 named entries; 43 categories | South and East Auckland focus; four unlabelled sections skipped; no source-stated dataset date |
| `repair` | Repair Network Aotearoa: `https://www.repairnetworkaotearoa.org.nz/dynamic-localrepaircafes_p_8500816c_6fb3_4424_8161_90ad1ae5b8b2_0_5000-sitemap.xml` | 46 sitemap URLs; Auckland library detail parsed live | Street addresses and schedules; event locations have no verified per-café coordinates |
| `tyrewise` | Tyrewise: `https://www.tyrewise.co.nz/participant_cat/collection-site/` | 108 archive entries across nine pages | Name, town/region taxonomy labels and operator detail link; no street address, hours or verified coordinates |
| `council` | Auckland Council: `https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/get-rid-unwanted-items.html` | Guidance not implemented | `item` returns exit 7; Council-only data selection returns exit 7 without fetching; consult the website manually |
| `techcollect` | TechCollect NZ: `https://techcollect.nz/` | Direct request returned HTTP 403; skipped | No scraping/bypass attempt; no verified structured feed |

`www.opengis.net` and `www.sitemaps.org` in metadata are XML namespaces,
not outbound requests.
Tyrewise operator detail links are returned for users; the CLI does not fetch
those links. This avoids guessing a street address from a territory or presenting the network's head-office coordinates as café sites.

## Parser details

- RecycleMap markers join `map_id` to `/maps`' `id` and `map_title`. Category IDs
  join the nested `/categories` tree and remain separate `categories`.
  Categories are mostly store brands, charges and restrictions, **not materials**.
  `description` retains acceptance/exclusion text; `hours` is extracted from its
  explicitly labelled opening-hours section. HTML is converted to visible text.
- WasteMINZ uses the KML namespace, point `coordinates` in lon,lat order,
  `name` and `description`. Battery chemistry, quantity and damage conditions
  stay in `details`; the generic `Batteries` label never overrides those rules.
- BRANZ requests `outSR=4326`, all attributes and geometry. Materials are
  accepted only from affirmative material flags. `Description` and
  `Accepted_Waste_Streams` stay in details. `editingInfo.dataLastEditDate` is
  converted from epoch milliseconds to `latest_data`. Transfer-limit responses
  fail explicitly rather than silently returning a partial facility list. Planned
  facilities are excluded. Service contractors and non-Existing status produce
  warnings, as they may not offer public drop-offs.
- E-Cycle JSON provides `store`, `address`, `address2`, `city`, `zip`, `lat`,
  `lng`, HTML `hours`, `description`, `fax` (service label) and operator `url`.
- Agrecovery uses `title.rendered` and `acf.ag_site_*`; only active sites are
  included (`acf: false` is treated as no fields). It pages until fewer than 100
  results or a confirmed WordPress `rest_post_invalid_page_number` HTTP 400,
  capped at 20 pages. Requests wait 10 seconds between pages to honour the
  declared `Crawl-delay: 10`. Other HTTP 400 responses remain failures.
- Beautification Trust joins `scene.sections` keys to category `sections`
  membership. Coordinates use each section's `mapView.center`; descriptions,
  addresses and operator links are retained. No map-style settings are cached.
- Repair café HTML uses visible text between “◀ Back” and “◀ Previous”. This
  avoids Wix's unrelated global business-location fields. Two readers and a
  250 ms pause per request bound load; the sitemap is capped at 150 pages.
  Individual detail failures are skipped with URL warnings; more than half
  failing makes the source fail.
- Tyrewise uses the sitemap-published taxonomy archive, not robots-disallowed
  `/registered-partners/_...` filter URLs. It parses article `entry-title` names
  and `region-*`/`city-*` classes, follows the published Next link (max 20 pages),
  and checks every next URL stays under the collection-site archive. A synthetic
  legacy `loop-item` fixture also tests the earlier card parser.

## Robots verification (2026-10-08)

Both scraped hosts were checked: Repair Network Aotearoa allows its sitemap
and `/localrepaircafes/` details for `User-agent: *`; Tyrewise allows
`/participant_cat/collection-site/` and its `/page/N/` paths, while explicitly
disallowing the former filter route. Its participant taxonomy sitemap lists
the archive. No disallowed filter pages are fetched. RecycleMap, E-Cycle and
Agrecovery robots also allow the API routes used here; Agrecovery declares the
10-second delay above. Google permits the published My Maps KML export.
Mapme robots returns 404 and ArcGIS robots returns 403; these are public data
API calls rather than website scraping. Council and TechCollect are not fetched.
Council remains in the metadata host list because the repository static audit requires hosts of returned URLs;
the runtime fetch allowlist excludes both unsupported sources.

## Council limitation

Council item guidance is not implemented. `item` deterministically returns
`unsupported_operation` (exit 7), without a request, and includes the public
Council URL for manual consultation. Council-only data selection also exits 7;
combined selection reports Council in `source_status` and warnings as partial
when working sources return records. Earlier network-blocked observations are
not a description of current availability.
Implementing guidance later requires a verified directory/item parser and
synthetic or appropriately licensed fixtures; no item taxonomy is guessed.

## Cache and failures

Only normalised directory records are cached for 24 hours under
`$XDG_CACHE_HOME/nz-recycling-locator` (fallback `~/.cache/nz-recycling-locator`).
Parser version 2 invalidates old shapes; writes use unique temporary files and
atomic replacement so concurrent runs do not share a temporary path. Cache data
contains public site information and retains source retrieval timestamps.
`--refresh` never substitutes stale cache after failure. `sources` always
fetches live and distinguishes record counts from repair sitemap URL counts.

A combined query continues with working sources and returns `result_status: partial`
plus per-source errors. If every selected source fails, or filtering leaves no
matches while a selected source failed, the command returns an error. HTTP
blocks/rate limits exit 4 (`retry_after` preserved), network failures exit 5 and
parser/schema changes exit 6. Council or TechCollect data selections exit 7
when they are the only selected sources; otherwise they appear in `source_status`
and warnings as partial (exit 0 when records remain). `sources` reports these as
skipped; skipped sources alone do not make the status listing partial. Spatial
filtering excludes unlocated records; GeoJSON without a spatial filter uses null
geometry for these entries.

`search` is textual discovery, so words may occur in exclusion text. `find`
uses material labels, but labels are still broad; show `details` before giving
specific disposal advice. Listings are not live stock, capacity or booking data.
Fixtures in `tests/fixtures/` are synthetic structure examples, clearly marked
in `capture-metadata.json`. Names, addresses and coordinates are invented; no
third-party contact details or page captures are redistributed.

An aggregate envelope uses a per-source `latest_data` object when several
sources are selected; a single-source envelope uses that source's stated date.

Multi-source `meta` uses the canonical skill source URL and earliest successful
source retrieval timestamp; per-source URLs and dates remain in `source_status`
and record provenance. This retains original cache dates. `result_status` avoids
the canonical runner's reserved top-level `status` failure marker. Unknown licence
and Retry-After values are omitted.

Cold-cache data queries and live status probes load up to four directories
concurrently and retain selection order for records and health. Repeated source
selectors are deduplicated, so one command never loads the same directory twice. Per-source pacing is unchanged, including
Agrecovery's 10-second inter-page delay and the two repair readers. The expected
cold-run budget is under 40 seconds on healthy endpoints (the runner caps commands
at 60 seconds); this is an operational target, not a network latency guarantee.
Single-source repair envelope provenance credits the sitemap, while record URLs
continue to identify the individual café pages. Error `retrieved_at` records the
attempted operation time, including invalid input and unsupported operations,
as required by `docs/contracts.md`; it does not claim a successful retrieval.
