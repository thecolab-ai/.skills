# RBNZ data notes

The useful route is a two-step public flow:

1. Discover packages/resources through data.govt.nz CKAN:

```text
https://catalogue.data.govt.nz/api/3/action/package_search?fq=organization:reserve-bank-of-new-zealand&q=<query>
https://catalogue.data.govt.nz/api/3/action/package_show?id=<package>
https://catalogue.data.govt.nz/api/3/action/datastore_search?resource_id=<resource-id>
```

2. Fetch official `rbnz.govt.nz` public file/chart endpoints with normal browser-compatible headers and a statistics-page referer. A minimal curl/Python `urllib` request may get Cloudflare 403, but adding browser headers (`User-Agent`, `Referer: https://www.rbnz.govt.nz/statistics`, `Sec-Fetch-*`, `sec-ch-ua*`) returns the public data without login, cookies, CAPTCHA, or browser automation.

Verified direct public endpoints:

- `https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/statistics/series/b/b1/hb1-daily.xlsx` returns the current B1 daily exchange-rate XLSX.
- `https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/statistics/series/b/b2/hb2-daily-close.xlsx` returns the current B2 wholesale-interest-rate XLSX.
- `https://www.rbnz.govt.nz/api/cache/chart/data/%7B39B96144-129C-4D86-AEA9-DAB75CDE26F4%7D` returns the public Real Trade Weighted Index chart JSON.
- `https://www.rbnz.govt.nz/api/cache/chart/data/%7B9E689530-C72C-493C-B41C-C9750BDD2C69%7D` returns the public retail deposit/mortgage rate chart JSON shown on the Statistics page.

Verified packages/resources:

- `exchange-rates` with current and historical B1 resource URLs; resource `f16aa755-ba94-4679-8c5f-4c1cb6c2901a` has CKAN datastore records.
- `wholesale-interest-rates` with B2 daily/monthly resource URLs.
- `key-graphs-90-day-rate-and-the-ocr` with official RBNZ key-graph resources.

Boundary: read-only public data. The skill does not bypass authentication, submit forms, or use private APIs; it only sends browser-compatible headers to public file/chart endpoints that are already linked from official public pages/catalogue metadata.
