# RBNZ data notes

Direct `rbnz.govt.nz` CSV/XLSX/statistics URLs returned Cloudflare 403 from this environment during the spike. The public RBNZ datasets are nevertheless discoverable through data.govt.nz CKAN:

```text
https://catalogue.data.govt.nz/api/3/action/package_search?fq=organization:reserve-bank-of-new-zealand&q=<query>
https://catalogue.data.govt.nz/api/3/action/package_show?id=<package>
https://catalogue.data.govt.nz/api/3/action/datastore_search?resource_id=<resource-id>
```

Verified packages/resources:

- `exchange-rates` with current and historical B1 resource URLs; resource `f16aa755-ba94-4679-8c5f-4c1cb6c2901a` has CKAN datastore records.
- `wholesale-interest-rates` with B2 daily/monthly resource URLs.
- search query `interest rates` finds `key-graphs-90-day-rate-and-the-ocr`.

Boundary: this skill reports official catalogue metadata and resource URLs. It does not bypass Cloudflare or guarantee direct RBNZ file downloads from every runtime.
