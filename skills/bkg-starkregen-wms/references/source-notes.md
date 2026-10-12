# Source notes

- Primary owner: Bundesamt für Kartographie und Geodäsie (BKG)
- Primary source URL: https://sgx.geodatenzentrum.de/wms_starkregen
- Catalogue page (not called by the CLI): https://gdz.bkg.bund.de/index.php/default/wms-hinweiskarte-starkregengefahren-wms-starkregen.html
- Data licence: Datenlizenz Deutschland – Namensnennung – Version 2.0 (https://www.govdata.de/dl-de/by-2-0)
- Declared outbound hosts: sgx.geodatenzentrum.de
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

The CLI calls only `https://sgx.geodatenzentrum.de/wms_starkregen`. Redirects
must stay on that HTTPS host. The User-Agent is
`thecolab-bkg-starkregen-wms/1.0 (+https://github.com/thecolab-ai/.skills)`.
Each command makes one GET, with a 10-second timeout. GetCapabilities is capped
at 750,000 bytes and 160 named layers. GetFeatureInfo is capped at 20,000
bytes, width 101, height 101, and one feature. There is no GetMap and no
national raster download. `robots.txt` on the host disallows
`/gdz_geoviewserver/` and `/gdz_geoviewserv/`; `/wms_starkregen` is not in that
list.

## Licence and product notes

On 2026-10-11, GetCapabilities Fees said the data are provided free of charge
under Datenlizenz Deutschland Namensnennung 2.0 and linked to
`https://www.govdata.de/dl-de/by-2-0`. AccessConstraints said there are no
access restrictions. The same Fees text asks for the source note
`© BKG (year of last retrieval) dl-de/by-2-0` and points to the BKG data-source
PDF and the OpenStreetMap supplementary attribution text. The CLI repeats the
source note using the retrieval year. It does not fetch those PDFs.

The catalogue page states the same Datenlizenz Deutschland Namensnennung 2.0
wording. The official documentation PDF
`https://sgx.geodatenzentrum.de/web_public/gdz/dokumentation/deu/hwk_srg.pdf`
(Stand 25.09.2026, fetched the same day) says Gesamtprodukt 2024, raster
resolution 1 metre, and that historical data are not available. That vintage is
not repeated in the WMS response, so the CLI does not emit `latest_data`. The
1 metre figure is the raster resolution, not a stated unit for
Geschwindigkeit. Do not label the number as m/s from this skill.

`geschwindigkeit_agw` is the extraordinary-event flow-velocity layer (the
service abstract describes a 100-year scenario). Depth, flow direction, the
extreme scenario, water-body layers, and transition layers are listed by
`layers` and are not queried.

## CRS axis

WMS 1.3.0 EPSG:4326 uses the CRS axis order latitude, longitude. The
capabilities bounding box on `geschwindigkeit_agw` has EPSG:4326 `minx` near
48.76 and `miny` near 5.38, so the server advertises latitude first. CRS:84 on
the same layer has those values swapped (longitude first) and is not requested.
The point command builds `BBOX=minLat,minLon,maxLat,maxLon` around the WGS84
point with a half-span of 0.0005 degrees. A longitude-first EPSG:4326
advertisement is a schema failure. Points whose window would cross a pole or
the antimeridian are invalid input.

## Values

A text/plain body of `Geschwindigkeit = 0.0` with a Land feature type such as
`ni_geschw_agw` is a measured zero. `no features were found` means the point
returned no Land feature; the velocity is absent, not zero. The token
`-9999.0` was observed inside some Land layers (for example North
Rhine-Westphalia cells on 2026-10-11). The capabilities document does not name
that token, and it is not a plausible flow velocity next to measured values
such as 0.0 and about 0.69. The parser treats that exact numeric token as no
data, keeps it in `source_token`, and does not emit it as `geschwindigkeit`.

## Fixtures

`tests/fixtures/capabilities-layers.xml` is a short excerpt of the public
capabilities document, including the Fees sentence and the EPSG:4326 and CRS:84
boxes. The text/plain fixtures are captured GetFeatureInfo bodies for a
measured zero, a non-zero value, no feature, and the -9999 token. They are
public BKG responses under the licence above. Attribute BKG. Empty and
malformed bodies are schema failures.

## Dedup

This host and operation are not implemented by `nz-ogc-records` or
`nz-data-catalogue`. The catalogue skill allow-lists `sgx.geodatenzentrum.de`
but does not call this WMS. Berlin and Frankfurt flood services are separate
contracts.
