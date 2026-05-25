---
name: nzpost-tracking
description: Track NZ Post parcels by tracking number using the public tools.nzpost.co.nz API. Returns current delivery status, last known location, and a full event timeline. No authentication required. Use when the task involves checking where an NZ Post parcel is, whether it has been delivered, or fetching the complete tracking history for a domestic or international tracking number.
---

# NZ Post Tracking

## Goal

Query the NZ Post public parcel tracking API to retrieve current delivery status and event history
for a given tracking number. No authentication required.

## Use this when

- A user wants to know where their NZ Post parcel is
- A user asks if a parcel has been delivered
- A user wants to see the full tracking history for a shipment
- A user has a domestic NZ Post tracking number or an international inbound tracking number routed through NZ Post
- A user asks "where is my package?" with an NZ Post or CourierPost number

## Do not use this for

- DHL, FedEx, UPS, or other non-NZ Post carriers
- NZ Post MyMail/standard letters (untracked items)
- Booking or scheduling courier pickups
- Redirecting or modifying delivery instructions

## Preferred workflow

1. Run `track <number>` for a human-readable status summary and event timeline
2. Add `--json` for machine-readable output suitable for piping or further processing
3. For international parcels, use the full tracking reference as provided by the sender

## CLI

Run with:

```bash
python3 skills/nzpost-tracking/scripts/cli.py <command> [flags]
```

### `track`

Track a parcel by its tracking number.

```bash
# Human-readable output
python3 skills/nzpost-tracking/scripts/cli.py track 00794210392715622565

# Machine-readable JSON
python3 skills/nzpost-tracking/scripts/cli.py track 00794210392715622565 --json

# International UPU format
python3 skills/nzpost-tracking/scripts/cli.py track EA123456789NZ --json
```

## Tracking number formats

NZ Post accepts a wide range of tracking number formats:

- 18-20 digit domestic numbers (e.g. `00794210392715622565`)
- 13-digit domestic short numbers
- UPU international format: 2 letters + 9 digits + 2 letters (e.g. `EA123456789NZ`)
- Alphanumeric codes (TP, RMA, RMC, SUN, CTC prefixes, etc.)

## Output fields (JSON)

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
- The endpoint is `tools.nzpost.co.nz/tracking/api/parceltrack/parcels` (unauthenticated)
- Requires `Referer: https://www.nzpost.co.nz/tools/tracking` header for CORS validation
- Python stdlib only (`urllib`, `json`, `re`, `argparse`)
- Delivered parcels retain their full tracking history indefinitely
