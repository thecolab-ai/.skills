# Auckland urban geological units

Authentication: none

Last verified: 2026-10-12

Primary source URL: https://data.gns.cri.nz/webmaps/gns/wfs

Outbound host: data.gns.cri.nz

## Endpoint

WFS 2.0.0 GetFeature on `https://data.gns.cri.nz/webmaps/gns/wfs`.

The only type name this skill sends is `gns:NZL-Urban_Auckland_geological_units`.
GetCapabilities on 2026-10-12 listed that name with title
`NZL-Urban_Auckland_geological_units`, default CRS `urn:ogc:def:crs:EPSG::2193`
(NZTM2000), and this WGS84 bounding box:

- lower corner longitude 174.39266830492312, latitude -37.3268036065307
- upper corner longitude 175.317103721445, latitude -36.69373976170905

The skill does not reproject. It asks for
`urn:ogc:def:crs:OGC:1.3:CRS84` on both `srsName` and the BBOX CRS. CRS84 axis
order is longitude, then latitude. A live count=1 request on
2026-10-12 for bbox `174.76,-36.86,174.78,-36.84` returned GeoJSON
positions in that order. The collection `crs` name was
`urn:ogc:def:crs:CRS::84`. The same server labelled an equivalent HTTP CRS84
request as `urn:ogc:def:crs:EPSG::4326` while still emitting longitude,
latitude. Both names are accepted. Positions are accepted only when they are finite
WGS84 longitude and latitude pairs and the ring is closed. The server bbox
filter decides intersection. An envelope within 0.002 degrees of the requested
box is kept. That slack covers the farthest miss in a full read of the 92
features for bbox `174.9,-37.05,174.98,-36.98` on 2026-10-12 (0.000809 degrees,
90 m, feature `.1490`). A farther envelope is omitted and counted in
`page.dropped_outside_bbox`. Those omissions do not discard units whose
envelopes overlap the box. If the server returned features and every envelope
is farther than the slack, the command is a schema failure. `page.matched` is
the server `numberMatched`. `page.returned` is the number of units in
`results`. NZTM easting/northing values fail closed.

`outputFormat` is `application/json`. `count` is `--limit` (1 to 5). There is
no `startIndex` parameter, so the command cannot walk the layer. A live
unfiltered count=1 response reported `numberMatched` 2639. Do not request the
whole layer.

The BBOX predicate is upstream intersection, not local containment. Vertices
may fall outside the box. A box with no intersection returns a FeatureCollection
with `numberMatched` 0 and no features. That is an empty result.

One command, one GET. Timeout 15 seconds. Body cap 524288 bytes. At most one
redirect, and only to `https://data.gns.cri.nz/webmaps/gns/wfs`. User-Agent:
`TheColab-gns-auckland-geology/1 (public WFS; bounded GetFeature)`.

## Fields

Each feature property is copied under the source key. The shapefile field
`descriptio` is the description; this skill does not rename it. `unit_code` is
required. A property-only read of all 2639 features on 2026-10-12 (`count=200`,
`propertyName=unit_code`, `startIndex` 0, 200, through 2600; `numberMatched`
2639) contained 103 distinct codes. The characters were letters, digits, `_`,
`+`, `~`, and a leading `?` on `?Pks~` (features `.1896` and `.1935`, stratigraphic
name `Kawaa Formation`). `?` is the GNS uncertainty marker. The skill keeps the
raw code and sets `uncertain` to true only when `unit_code` starts with `?`.
A question mark anywhere else, including `tl~?x`, is rejected. A code is at
most 41 characters: a letter or digit plus at most 40 characters from
`A-Za-z0-9_./~+-`, or `?`, a letter or digit, and at most 39 characters from
that set. `.` `/` `-` did not occur in the 2639-feature read; they remain
allowed after the first letter or digit. An empty value, a leading `~` or
`+`, whitespace, markup, or any other character is a schema failure. Bbox `174.76,-36.86,174.78,-36.84` with
`count=5` returned five features (`numberMatched` 17). `tl~` and `Q1nc` had
`strat_unit` null; `Mwe` was East Coast Bays Formation. Null strings are
omitted, and a missing stratigraphic name is not a schema failure. `area`,
`perimeter`, `geol_units`, `geol_uni_1`, and `scale` are passed through as
finite numbers when present. The WFS properties do not name units for area or
perimeter, and this skill does not convert them. `scale` is
the source value (observed 50000 on a 1:50 000 map sheet) and is not treated as
a measured length. `strat_age` is the source code, such as `Mi`, and is not
expanded. The response `timeStamp` is the WFS response time, not a map revision
date, so results omit `latest_data`.

`geometry_name` is copied when it is a short string. Unknown scalar properties
are kept and named in `warnings`. Nested unknown values are a schema failure.

## Licence

GetCapabilities `ows:AccessConstraints`, read 2026-10-12, fees `NONE`:

> Copyright GNS Science 2014. These map data are released free under the Creative Commons Attribution 3.0 New Zealand (CC-BY 3.0) Licence - http://creativecommons.org/licenses/by/3.0/nz/

Results set `meta.licence` to `Creative Commons Attribution 3.0 New Zealand (CC-BY 3.0)`.
That string is this verified service constraint for the Auckland units layer.
It is not re-read from each feature. The skill's MIT licence is the code
licence, not the data licence. Attribute GNS Science.

## Errors

| Condition | Exit | Type |
|---|---:|---|
| Bad bbox, bad limit, unknown fixture name | 2 | invalid_input |
| HTTP 429 | 4 | blocked |
| Timeout, DNS failure, HTTP 5xx, body over 512 KiB | 5 | upstream_unavailable |
| Malformed JSON, XML exception, wrong CRS, NZTM coordinates, extra features, unclosed ring, every feature far outside the box | 6 | schema_failure |
| Redirect or final URL off the WFS path | 7 | unsupported_operation |

Fixtures are synthetic. A fixture warning is present on success. An upstream
outage, an empty live collection, or a licence that cannot be stated is not a
pass.

## Other GNS surfaces

`gns-hazards-nz` queries active-fault and ShakingLayers services on
`gis.gns.cri.nz` and `shakinglayers.geonet.org.nz`. Its notes mention
`https://data.gns.cri.nz/af/` for the active-fault web app. `nz-arcgis` allows
`gis.gns.cri.nz`. Neither issues a WFS GetFeature for
`gns:NZL-Urban_Auckland_geological_units`.
