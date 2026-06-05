# LINZ Data Service API notes

Public Koordinates services API base:

```text
https://data.linz.govt.nz/services/api/v1/
```

Verified endpoints:

- `layers/?q=<query>` returns public layer search results.
- `layers/<id>/` returns full layer metadata, description, licence, categories, tags, permissions, and HTML/canonical URLs.
- `layers/<id>/services/` returns advertised service endpoints such as CS-W, WFS, WMTS, ArcGIS/XYZ links, plus whether each uses no auth or API key auth.

Live probe: `layers/?q=address` returned `NZ Addresses` with id `123113`, public_access `download`, and user_permissions including `find`, `view`, `download`.

Boundary: this skill is catalogue/read-only metadata and service discovery. Do not create exports or use API-key service URLs unless the user provides a legitimate key/config explicitly.
