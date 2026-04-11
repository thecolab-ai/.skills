# Cyclone Tracking Reference

## Data indicators to watch

| Indicator | Threshold | Meaning |
|---|---|---|
| Pressure | < 990 hPa | Tropical cyclone territory |
| Pressure drop | > 3 hPa/hr | Rapid intensification — DANGER |
| Sustained winds | > 63 km/h | Tropical cyclone |
| Sustained winds | > 118 km/h | Severe tropical cyclone |
| Storm surge | Wave height + tide level | Coastal flooding risk |

## CLI commands for cyclone monitoring

```bash
# Pressure + extreme wind + storm surge data
npx tsx skills/metservice-nz/scripts/cli.ts cyclone auckland

# Continuous polling — alerts on changes
npx tsx skills/metservice-nz/scripts/cli.ts watch wellington

# Active MetService alerts
npx tsx skills/metservice-nz/scripts/cli.ts warnings

# Wave height / surge data
npx tsx skills/metservice-nz/scripts/cli.ts marine auckland

# Pressure trend (12h history + 12h forecast)
npx tsx skills/metservice-nz/scripts/cli.ts pressure christchurch
```

## MetOcean variables for cyclone tracking

- `air.pressure.at-sea-level` — pressure drop is the #1 cyclone indicator
- `wind.speed.at-10m` — sustained winds
- `wind.speed.gust.at-10m` — gusts
- `wind.direction.at-10m` — wind direction shifts
- `wave.height` — storm surge / swell
- `wave.height.primary-swell` — incoming ocean swell
- `wave.period.peak` — long period = distant storm energy
- `precipitation.rate` — rainfall intensity

## Official NZ sources

- MetService warnings: https://www.metservice.com/warnings/home
- MetService severe weather outlook: https://www.metservice.com/warnings/severe-weather-outlook
- MetService tropical cyclone tracker: https://www.metservice.com/marine-surf/tropical-cyclones
- NIWA: https://www.niwa.co.nz/
- Civil Defence / NEMA: https://www.civildefence.govt.nz/

## Regional / Pacific sources

- RSMC Nadi (Regional Specialised Meteorological Centre for Pacific tropical cyclones): https://www.met.gov.fj/
- Australia BoM tropical cyclone tracker: http://www.bom.gov.au/cyclone/
- Joint Typhoon Warning Center (JTWC): https://www.metoc.navy.mil/jtwc/jtwc.html

## Best visual trackers

- Windy.com — best visual with pressure/wind overlays: https://www.windy.com/?-36.9,175.1,7
- Zoom.earth — real satellite imagery: https://zoom.earth/
- Cyclocane: https://www.cyclocane.com/
- GDACS (Global Disaster Alert): https://www.gdacs.org/
