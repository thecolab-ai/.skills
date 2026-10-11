# Berlin Starkregengefahrenkarte WFS

- Authentication: none
- Last verified: 2026-10-11

Primary source URL: https://gdi.berlin.de/services/wfs/ua_srgk

Outbound host: gdi.berlin.de

The service is the Geoportal Berlin WFS `ua_srgk`, version 2.0.0. `types` calls
GetCapabilities. `areas` calls GetFeature for `ua_srgk:a_modellgebiete` only.
The live smoke also sends one `resultType=hits` request with `count=1`. No
command sends `startIndex` or follows a `next` link.

## Licence and provider

GetCapabilities on 2026-10-11 stated:

- Fees: the dataset is published under CC-BY-4.0-Namensnennung International
  Public License. The legal-code page named there is
  https://creativecommons.org/licenses/by/4.0/legalcode.de
- AccessConstraints: Es gelten keine Zugriffsbeschränkungen.
- ProviderName: Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen Berlin

The required attribution (Quellenvermerk) is:

Gebiete Moabit, Flughafensee, Neukölln, Rudow, Kladow/Gatow: Berliner Wasserbetriebe / Starkregengefahrenkarte; Gebiete Niederschönhausen Ost, Obersee, Frankentaler Ufer: Geoportal Berlin / Starkregengefahrenkarte / Starkregengefahrenkarte

`types` reads that sentence from the live Fees text and fails if the CC BY 4.0
marker, the no-access-restriction sentence, the provider name, or the
attribution anchors are absent. `areas` makes only the feature request, so it
repeats this verified attribution instead of fetching Fees again.

The dataset page https://daten.berlin.de/datensaetze/starkregengefahrenkarte-wfs-1aa4f1ef
returned HTTP 403 with a connection challenge on 2026-10-11. That page was not
read and is not an outbound host for this skill. The WFS Fees text is the
licence evidence.

## Feature types

Confirmed names, all defaulting to EPSG:25833:

- `ua_srgk:ca_fliessgeschwindigkeit_aussergewoehnlich`
- `ua_srgk:da_fliessgeschwindigkeit_extrem`
- `ua_srgk:ba_fliessgeschwindigkeit_selten`
- `ua_srgk:a_modellgebiete`

The first three are velocity surfaces. This skill does not download them.
Model-area output keeps the envelope only. Envelope values are easting and
northing in metres in the source CRS. They are not WGS84 degrees, and this
skill does not reproject them.

On 2026-10-11, `resultType=hits` reported `numberMatched` 8. A single
`count=8` read, about 496 KiB including polygons that were not stored, returned
these areas:

| id | name |
|---|---|
| 1 | Neukölln |
| 2 | Niederschönhausen Ost |
| 3 | Frankentaler Ufer |
| 4 | Obersee |
| 5 | Moabit (EZG_APw Bln VIII) |
| 6 | Flughafensee |
| 7 | Rudow |
| 8 | Kladow/Gatow |

The fixture `tests/fixtures/area-neukoelln.xml` is a CC BY 4.0 excerpt of area 1
with the polygon replaced by a short dummy `posList`. The parser must not copy
that geometry into results. `nz-ogc-records` does not call this host.
`nz-data-catalogue` only lists `gdi.berlin.de` inside a host inventory.
