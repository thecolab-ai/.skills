# Christchurch Bin Schedule API notes

This skill is an unofficial wrapper around the public Christchurch City Council collection-day APIs.

## Source and auth

- Collection-day search page: `https://ccc.govt.nz/services/rubbish-and-recycling/collections/`
- Address suggest API: `https://opendata.ccc.govt.nz/CCCSearch/rest/address/suggest?q=<query>`
- Collection data API: `https://ccc.govt.nz/services/rubbish-and-recycling/collections/getProperty?ID=<RatingUnitID>`
- Auth model: **no credentials required**

## Endpoint details

### Address suggest (`CCCSearch/rest/address/suggest`)

- **Base URL:** `https://opendata.ccc.govt.nz/CCCSearch/rest/address/suggest`
- **Method:** GET
- **Query params:** `q=<search string>`
- **Response:** JSON array of address objects
- **No bot protection** — works from any IP

Response shape:
```json
[
  {
    "StreetAddressID": 145121,
    "FullStreetAddress": "53 Hereford Street, Central City, Christchurch 8013",
    "FullPostalAddress": "53 Hereford Street, Central City, Christchurch 8013",
    "RatingUnitID": 86089,
    "Geometry": {
      "coordinates": [1570253.874104, 5180066.714013],
      "crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::2193"}, "type": "Name"},
      "type": "Point"
    }
  }
]
```

The `RatingUnitID` is the key value needed for the collection endpoint.

### Collection data (`getProperty`)

- **Base URL:** `https://ccc.govt.nz/services/rubbish-and-recycling/collections/getProperty`
- **Method:** GET
- **Query params:** `ID=<RatingUnitID>`
- **Response:** JSON object
- **Bot protection:** Incapsula — works from residential NZ IPs, may block datacenter/VPN IPs

Response shape:
```json
{
  "id": "86089",
  "address": "53 Hereford Street Central City Christchurch",
  "latitude": -43.53192,
  "longitude": 172.63143,
  "bins": {
    "containers": [
      {
        "container_type": "140L WB",
        "material": "Garbage",
        "serial_no": "G012147",
        "tag": "E20000191505019028200368",
        "status": "Active"
      }
    ],
    "routes": [
      {
        "material": "Garbage",
        "day_of_week": "Tuesday",
        "customer_group": "WK2 TUE"
      }
    ],
    "collections": [
      {
        "next_planned_date": "2026-06-16",
        "next_planned_date_app": "2026-06-16",
        "material": "Garbage",
        "pick_up_group": "205",
        "out_of_date": "False"
      }
    ]
  }
}
```

#### Key fields

- **`bins.containers[]`** — Physical bins registered to the property
  - `material`: `Garbage`, `Recycle`, or `Organic`
  - `container_type`: e.g. `140L WB` (wheelie bin), `240L WB`, `80L WB`
  - `tag`: RFID tag ID

- **`bins.routes[]`** — Regular collection schedule
  - `material`: bin type
  - `day_of_week`: day of week for collection
  - `customer_group`: route group identifier (e.g. `WK2 TUE` = Week 2 Tuesday)

- **`bins.collections[]`** — Specific planned collection dates
  - `next_planned_date`: date in ISO format (`YYYY-MM-DD`)
  - `next_planned_date_app`: date shown in the CCC app (sometimes differs)
  - `material`: bin type
  - `pick_up_group`: collection group number
  - `out_of_date`: `"True"` or `"False"` — filter to `"False"` for current/future

## Christchurch collection model

Under the 2024 national standardisation, Christchurch uses a **three-bin system**:

| Bin | Colour | Contents | Frequency |
|-----|--------|----------|-----------|
| Rubbish | Red | General waste | Fortnightly |
| Recycling | Yellow | Plastics #1,#2,#5, cans, glass, paper/cardboard | Fortnightly |
| Organics | Green | Food scraps, garden waste | Weekly (where available) |

All three bins are typically collected on the **same day of the week**. Rubbish and recycling rotate on alternating fortnightly schedules (Week A / Week B).

## Incapsula bot protection

The `getProperty` endpoint is behind Imperva/Incapsula bot detection. This is **IP-based**:

- **Residential NZ IPs**: Generally work without issues (the Home Assistant community has been using this endpoint for years)
- **Datacenter/VPN IPs**: Likely blocked with HTTP 403
- **Cooldown**: A blocked IP may work again after a cooldown period

The address suggest endpoint has no bot protection and works from any IP.

## Stability and safety

- Treat dates as live current snapshots from CCC, not historical or guaranteed data
- Public holidays can shift collection dates — the `next_planned_date` should reflect this
- The `getProperty` response shape could change — the CLI parses defensively
- Avoid high-volume scraping; rate-limit requests
- Do not use this skill for account changes or service requests
- The `next_planned_date_app` field exists for the CCC mobile app and may differ from `next_planned_date`
