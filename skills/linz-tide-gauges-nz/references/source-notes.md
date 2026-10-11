# Source notes

- Primary owner: Toitū Te Whenua Land Information New Zealand (LINZ)
- Primary source: https://sealevel-data.linz.govt.nz/index.html?tidegauge=AUCT
- Data licence: Creative Commons Attribution 3.0 New Zealand (CC BY 3.0 NZ)
- Declared outbound hosts: sealevel-data.linz.govt.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

Catalogue row S1873, "LINZ tide-gauge archive — Auckland AUCT (Devonport Naval Base)", points at this host. The downloads page states CC BY 3.0 NZ. Attribute readings to Land Information New Zealand. Endpoint shape, UTC semantics, and known limits are in [api-notes.md](api-notes.md).

Live commands only call `listGauges`, `getGaugeData/{gauge}`, `listDatasetFiles/{gauge}/{year}/{sensor}`, and one matching daily zip under `/tidegauge/`. Annual, day-of-year, and month bundles named in that file list are labeled and are not fetched. A blank directory row is not a file. Redirects and archive paths must stay on `sealevel-data.linz.govt.nz`. A fixture run reads only a file under `tests/fixtures/` and labels `retrieval_kind` as `fixture`. Heights from a live or zip reading are metres above gauge zero (TG0). UTC gauges keep CSV minutes as Zulu. Scott Base minutes stay on the NZST offset stated in the gauge text.
