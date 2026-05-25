---
name: nzpost
description: Query NZ Post public APIs for parcel tracking, PostShop/parcel-collect/postbox location search, and address/postcode lookup. No authentication required. Use when the task involves tracking an NZ Post parcel, finding a nearby PostShop or parcel-collect point, looking up a New Zealand delivery address or postcode, or fetching complete tracking history for a domestic or international tracking number.
---

# NZ Post

## Goal

Query NZ Post public APIs for parcel tracking, location search (PostShops, parcel-collect points, postboxes), and address/postcode lookup. No authentication required.

## Use this when

- A user wants to know where their NZ Post parcel is
- A user asks if a parcel has been delivered
- A user wants to see the full tracking history for a shipment
- A user has a domestic NZ Post tracking number or an international inbound tracking number routed through NZ Post
- A user asks "where is my package?" with an NZ Post or CourierPost number
- A user wants to find a PostShop, parcel-collect point, or postbox near a location
- A user wants to look up a New Zealand address or postcode

## Do not use this for

- DHL, FedEx, UPS, or other non-NZ Post carriers
- NZ Post MyMail/standard letters (untracked items)
- Booking or scheduling courier pickups
- Redirecting or modifying delivery instructions

## Preferred workflow

1. Run `track <number>` for a human-readable status summary and event timeline
2. Run `locations --near "SUBURB"` to find nearby NZ Post facilities
3. Run `address "QUERY"` to look up NZ delivery addresses and postcodes
4. Add `--json` to any command for machine-readable output suitable for piping

## CLI

Run with:

```bash
python3 skills/nzpost/scripts/cli.py <command> [flags]
```

### `track`

Track one or more parcels by tracking number.

```bash
# Human-readable output
python3 skills/nzpost/scripts/cli.py track 00794210392715622565

# Machine-readable JSON
python3 skills/nzpost/scripts/cli.py track 00794210392715622565 --json

# Multiple parcels
python3 skills/nzpost/scripts/cli.py track 00794210392715622565 00000000000000000000 --json

# International UPU format
python3 skills/nzpost/scripts/cli.py track EA123456789NZ --json
```

### `locations`

Find PostShops, parcel-collect points, and postboxes near a location.

```bash
# By place name
python3 skills/nzpost/scripts/cli.py locations --near "Clevedon, Auckland" --limit 5

# By coordinates
python3 skills/nzpost/scripts/cli.py locations --lat -36.8485 --lon 174.7633 --limit 10

# By keyword
python3 skills/nzpost/scripts/cli.py locations --keyword "Auckland CBD" --limit 10

# Filter by type
python3 skills/nzpost/scripts/cli.py locations --near "Auckland CBD" --type postshop

# JSON output
python3 skills/nzpost/scripts/cli.py locations --near "Clevedon" --json
```

### `address`

Look up NZ delivery addresses and postcodes.

```bash
# Human-readable list
python3 skills/nzpost/scripts/cli.py address "Papakura" --limit 10

# JSON output
python3 skills/nzpost/scripts/cli.py address "Papakura" --json
```

## Tracking number formats

NZ Post accepts a wide range of tracking number formats:

- 18 or 20 digit domestic numbers (e.g. `00794210392715622565`)
- 13-digit domestic short numbers
- UPU international format: 2 letters + 9 digits + 2 letters (e.g. `EA123456789NZ`)
- Alphanumeric codes (TP, RMA, RMC, SUN, CTC prefixes, etc.)

## Output fields (JSON, track)

| Field | Description |
|-------|-------------|
| `tracking_reference` | The normalised tracking number |
| `status` | Current delivery status label |
| `last_updated` | ISO 8601 UTC timestamp of the latest event |
| `last_depot` | Last known depot name, if available |
| `event_count` | Total number of tracking events |
| `events[]` | Full event timeline, oldest first |
| `events[].date_time` | UTC timestamp |
| `events[].status` | Short status label |
| `events[].description` | Longer description (HTML stripped) |
| `events[].depot_name` | Depot name, if applicable |
| `events[].run_name` | Courier run or area name, if applicable |
| `events[].edifact_code` | Internal EDIFACT event code |

## Resources

- CLI entrypoint: `scripts/cli.py`
- API discovery notes: `references/api-notes.md`

## Notes

- No API key or authentication required
- Tracking endpoint: `tools.nzpost.co.nz/tracking/api/parceltrack/parcels`
- Locations endpoint: `api.nzpost.co.nz/digital/postshop-locations/v2/locations`
- Address endpoint: `tools.nzpost.co.nz/legacy/api/suggest` (requires Referer header)
- Python stdlib only (`urllib`, `json`, `re`, `argparse`)
- Delivered parcels retain their full tracking history indefinitely
