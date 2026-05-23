# NZ Libraries API Notes

This skill is intentionally read-only. It does not log in, place holds, renew items, or call patron/account endpoints.

## Support matrix

| Network | Backend | Catalogue search | Book detail | Availability | Branches/hours |
| --- | --- | --- | --- | --- | --- |
| Auckland Libraries | Vega / Innovative Interfaces | Yes | Yes | Branch-level for physical tabs | Yes |
| Wellington City Libraries | Spydus | Yes | Yes, search-scoped ids | XHLD table for search-scoped ids | Yes |
| Christchurch City Libraries | BiblioCommons | Yes | Yes | Bib-level status/counts | Yes |
| Hamilton City Libraries | SirsiDynix Enterprise / Kotui | Yes | Best-effort public detail page | Best-effort item fields | Not wired |
| Dunedin Public Libraries | SirsiDynix Enterprise / Kotui | Yes | Best-effort public detail page | Best-effort item fields | Not wired |
| Tauranga City Libraries | SirsiDynix Enterprise / Kotui | Yes | Best-effort public detail page | Best-effort item fields | Not wired |

## Auckland Libraries

Public site:

- Main site: `https://www.aucklandlibraries.govt.nz/`
- Catalogue: `https://discover.aucklandlibraries.govt.nz/`
- Branch hours: `https://www.aucklandlibraries.govt.nz/en/locations-and-services.html`

Backend: Vega / Innovative Interfaces.

Discovery notes:

- The catalogue app exposes `config.js` with `API_URL = https://ap.iiivega.com`.
- `https://discover.aucklandlibraries.govt.nz/lookup` returns the customer code `elgar`.
- The app constructs the API customer domain as `elgar.ap.iiivega.com`.
- Requests need headers:
  - `iii-customer-domain: elgar.ap.iiivega.com`
  - `iii-host-domain: discover.aucklandlibraries.govt.nz`
  - `api-version: 2` for search/detail
  - `api-version: 1` for drawer availability/location endpoints

Endpoint shapes:

- Search: `POST https://ap.iiivega.com/api/search-result/search/format-groups`
  - JSON body: `{"searchText":"Eleanor Catton","searchType":"everything","pageNum":0,"pageSize":5,"resourceType":"FormatGroup"}`
  - Response: `totalResults`, `data[]`; each item is a `FormatGroup` with `id`, `title`, `publicationDate`, `primaryAgent`, `identifiers`, and `materialTabs`.
- Detail: `GET https://ap.iiivega.com/api/search-result/search/format-groups/{formatGroupId}`
- Availability locations: `GET https://ap.iiivega.com/api/search-result/drawer/format-groups/{formatGroupId}/locations?tab={tabName}`
  - Response: `available[]` and `unavailable[]` arrays with branch code/label, item location, and call number.

Branch/hours:

- The public locations page embeds library cards in HTML with `<h3>Branch Library</h3>`, weekday `<li>` hours, and address paragraphs.

## Wellington City Libraries

Public site:

- Main site: `https://www.wcl.govt.nz/`
- Catalogue: `https://catalogue.wcl.govt.nz/`
- Branches: `https://www.wcl.govt.nz/visit/locations/`
- Opening hours: `https://www.wcl.govt.nz/visit/opening-hours/`

Backend: Spydus.

Endpoint shapes:

- Search: `GET https://catalogue.wcl.govt.nz/cgi-bin/spydus.exe/ENQ/OPAC/BIBENQ?ENTRY={query}&ENTRY_NAME=BS&ENTRY_TYPE=K&SORTS=SQL_REL_BIB&GQ={query}&NRECS={limit}`
- Search result ids are session-scoped pairs from detail links: `{setId}:{recordId}`.
- Detail: `GET /cgi-bin/spydus.exe/FULL/OPAC/BIBENQ/{setId}/{recordId},1`
- Availability: `GET /cgi-bin/spydus.exe/XHLD/OPAC/BIBENQ/{setId}/{recordId}?RECDISP=REC`

Notes:

- The CLI returns Wellington ids exactly as search provides them. Use the id immediately for `book` or `availability`.
- WCL blocks minimal/default curl headers with 403; normal browser-like `User-Agent`, `Accept`, and `Accept-Language` headers work.

## Christchurch City Libraries

Public site:

- Main site: `https://christchurchcitylibraries.com/`
- Catalogue: `https://christchurch.bibliocommons.com/`
- Branches: `https://christchurch.bibliocommons.com/locations/`

Backend: BiblioCommons.

Endpoint shapes:

- Search page: `GET https://christchurch.bibliocommons.com/v2/search?query={query}&searchType=smart`
- Record page: `GET https://christchurch.bibliocommons.com/v2/record/{bibId}`
- Both pages embed application state as `<script type="application/json" data-iso-key="_0">...</script>`.
- Useful JSON paths:
  - `search.catalogSearch.results[]` with `representative` and `manifestations`
  - `entities.bibs.{bibId}.briefInfo`
  - `entities.bibs.{bibId}.availability`

Branch/hours:

- Public fragment: `GET https://christchurch.bibliocommons.com/locations/locations?limit=0&fragment=true`
- The fragment contains branch names, addresses, phone/email, status, hours, and facilities.

Limitations:

- The lightweight parser exposes BiblioCommons title-level availability counts/status from SSR JSON. It does not currently fetch per-item drawer rows.

## Hamilton, Dunedin, and Tauranga

Public catalogue tenant:

- Hamilton: `https://ent.kotui.org.nz/client/en_AU/hamilton/`
- Dunedin: `https://ent.kotui.org.nz/client/en_AU/dunedin/`
- Tauranga: `https://ent.kotui.org.nz/client/en_AU/tauranga/`

Backend: SirsiDynix Enterprise via Kotui.

Endpoint shapes:

- Search: `GET https://ent.kotui.org.nz/client/en_AU/{profile}/search/results?qu={query}`
- Result cards include hidden Enterprise ids such as `ent://SD_ILS/0/SD_ILS:4807407`.
- Detail: `GET https://ent.kotui.org.nz/client/en_AU/{profile}/search/detailnonmodal/ent:$002f$002f{source}$002f0$002f{rawId}/one`

Normalization:

- CLI ids preserve the raw Enterprise id after the network prefix, for example `hamilton:SD_ILS:4807407`.
- Detail pages expose title metadata and, on some records, child item fields such as location/collection, barcode, and item type.

Limitations:

- Exact branch-level availability varies by Kotui tenant and record type.
- Branch locations/hours for Hamilton, Dunedin, and Tauranga are not wired in this lightweight version.

## Backend pattern notes

- BiblioCommons often exposes catalogue state through public server-rendered JSON even when there is also a JSON API gateway.
- SirsiDynix Enterprise pages are HTML-first; ids are often session or Enterprise-resource encoded.
- Koha and Spydus installations often expose JSON endpoints, but the networks wired here did not require Koha.
- Spydus availability is most useful when using the exact search-scoped id returned by the current result page.
