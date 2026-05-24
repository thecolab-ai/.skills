# CarJam NZ source notes

## Source

- Website: `https://www.carjam.co.nz/`
- Public vehicle report page shape: `https://www.carjam.co.nz/car/?plate=<PLATE>`
- Also observed to accept `vin=<VIN>` and `chassis=<CHASSIS>` query keys for direct lookup flows.

This skill uses only the public, no-login HTML page that CarJam renders for a vehicle. It does not call booking/payment/account/report-purchase endpoints.

## Extraction pattern

The public page renders many vehicle fields as HTML rows using:

```html
<span class="key" data-key="make">Make:</span>
<span class="value">TOYOTA</span>
```

The CLI extracts the `data-key` and visible value text from each row. It returns:

- `summary` — curated useful public fields for agent/human use
- `fields` — all parsed public fields when `--raw` is requested
- `locked_fields` — fields whose visible value is a CarJam gate such as `Get Report`, `May be in Report`, or `Subscribe`
- `alerts` — a few prominent free-text status snippets when present, such as WOF/licence/registration cancellation messages

## Read-only/privacy boundary

Do not add commands that:

- purchase or trigger a paid report
- create an account or log in
- subscribe to plate history or reminders
- submit stolen-vehicle reports or any write action
- scrape owner names/addresses or try to bypass paid report gates
- store bulk vehicle datasets

For gated fields, preserve the gate marker and explain that the information is not visible in the public/basic page.

## Stability caveats

- CarJam does not present this as a stable public API; it is public HTML parsing.
- Some fields vary by vehicle and by whether the free/basic page exposes them or replaces them with a report gate.
- Public vehicle status can change; include the CarJam source URL and timestamp/context in user-facing reports when important.
- The CLI validates identifier length/characters only lightly; it relies on CarJam for actual vehicle existence and field availability.

## Live verification examples

Verified during creation:

```bash
python3 skills/carjam-nz/scripts/cli.py lookup ABC123 --json
python3 skills/carjam-nz/scripts/cli.py lookup KMM42
python3 skills/carjam-nz/scripts/cli.py batch ABC123 KMM42 --json
```

Representative public result at creation time:

- `ABC123` resolved to `1997 MITSUBISHI DELICA SPACE GEAR`
- Colour: `Green`
- VIN: `7A8CJ0P0797205527`
- Registration status: `Cancelled`

Representative gate behaviour:

- `KMM42` resolved to `2006 TOYOTA IST`
- Several fields such as odometer/registration/WOF showed CarJam report-gated values rather than public values
