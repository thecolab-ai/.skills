# data.govt.nz API notes

Public base:

```text
https://catalogue.data.govt.nz/api/3/action/
```

This is a CKAN-compatible API and needs no key for catalogue reads.

Verified endpoints:

- `package_search?q=<query>&rows=<n>` - dataset search
- `package_show?id=<dataset-name-or-id>` - dataset metadata and resources
- `organization_list?all_fields=true` - agencies/organisations
- `datastore_search?resource_id=<resource-id>&limit=<n>` - tabular resource preview when the resource is in CKAN datastore

Live probe showed `package_search?rows=0` reported more than 31k datasets. Resource URLs can point to external agency systems and may have their own licences/availability.

Boundary: read-only catalogue/data preview. Do not mutate packages/resources or assume linked source data has the same licence as catalogue metadata without checking fields.
