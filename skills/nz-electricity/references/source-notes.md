# Source notes

- Primary owner: Electricity Authority and participating market operators
- Primary source: https://api.em6.co.nz/ords/em6/data_api
- Declared outbound hosts: api.em6.co.nz,api.integration.countiesenergy.co.nz,contact.co.nz,emidatasets.blob.core.windows.net,media.genesisenergy.co.nz,outage-centre.api.vector.co.nz,outagereporter.api.vector.co.nz,outages.powerco.co.nz,outages.topenergy.co.nz,public.tableau.com,server.ourpower.co.nz,www.auroraenergy.co.nz,www.ea.govt.nz,www.emi.ea.govt.nz,www.mercury.co.nz,www.meridianenergy.co.nz,www.nzier.org.nz,www.oriongroup.co.nz,www.unison.co.nz,www.welectricity.co.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-12

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

## Solar installation CSVs

Checked on 12 October 2026:

- Region CSV `SolarInstallationsByRegion.csv` returned HTTP 200 from `emidatasets.blob.core.windows.net`, 11270 bytes, with header `RegionType,RegionCode,Region,MarketSegment,ICPs,GenerationCapacityKilowattsAvg,GenerationCapacityKilowattsSum`. New Zealand residential ICPs were a positive integer (85455 on that fetch).
- Street CSV `SolarInstallationsByStreet.csv` returned HTTP 200, content-length 4269866, 79052 data rows. The header has Statistical Area 2 code and name, street, market segment, ICPs, and kilowatt capacity. It has no Region column. The first data row uses the literal ICP text `3 or less`.
- Electricity Authority copyright statement `https://www.ea.govt.nz/copyright-disclaimer-transparency/` says site copyright material is licensed CC-BY 4.0 unless a specific item or collection says otherwise. The exception list covers logos, site design and imagery, third-party letters, reports, submissions and section 46 responses, and market-operator agreements. It does not name the solar-installation CSVs. Attribute the Electricity Authority.
- `energy-hardship-nz` already allowlists the same blob host for hardship and disconnection material. That is a different operation. GUEHMT `dg-trends` remains the distributed-generation trend series and does not read these two files.

Parser fixtures under `tests/fixtures/solar-region-sample.csv` and `tests/fixtures/solar-street-sample.csv` use the published headers and the literal suppression token. Street names in the street fixture are synthetic. They are not a copy of the full street file.
