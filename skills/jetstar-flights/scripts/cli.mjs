#!/usr/bin/env node
// Search public Jetstar fare-cache flight availability.
// Read-only: no login, booking creation, seat holds, or checkout.

const API = 'https://digitalapi.jetstar.com/v1/farecache/flights/batch/availability-with-fareclasses';

function usage(exitCode = 0) {
  const out = exitCode ? console.error : console.log;
  out(`Usage: node skills/jetstar-flights/scripts/cli.mjs search ORIGIN DESTINATION DATE [flags]\n\nCommands:\n  search ORIGIN DESTINATION DATE   Search one-way fares for a date (YYYY-MM-DD)\n\nFlags:\n  --days N        Number of days to search from DATE (default: 1)\n  --adults N      Adult passenger count used for fare cache paxCount (default: 1)\n  --limit N       Max flights to print in human output (default: 10)\n  --json          Emit machine-readable JSON\n\nExamples:\n  node skills/jetstar-flights/scripts/cli.mjs search AKL WLG 2026-07-13 --days 7\n  node skills/jetstar-flights/scripts/cli.mjs search AKL CHC 2026-07-13 --json`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  if (argv.length === 0 || argv.includes('--help') || argv.includes('-h')) usage(0);
  const command = argv.shift();
  if (command !== 'search') usage(1);
  const [origin, destination, date] = argv.splice(0, 3);
  if (!origin || !destination || !date) usage(1);
  const opts = { command, origin: origin.toUpperCase(), destination: destination.toUpperCase(), date, days: 1, adults: 1, limit: 10, json: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--json') opts.json = true;
    else if (arg === '--days') opts.days = Number(argv[++i]);
    else if (arg === '--adults') opts.adults = Number(argv[++i]);
    else if (arg === '--limit') opts.limit = Number(argv[++i]);
    else throw new Error(`Unknown flag: ${arg}`);
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(opts.date)) throw new Error('DATE must be YYYY-MM-DD');
  if (opts.origin === opts.destination) throw new Error('origin and destination must differ');
  if (!Number.isInteger(opts.days) || opts.days < 1 || opts.days > 31) throw new Error('--days must be an integer from 1 to 31');
  if (!Number.isInteger(opts.adults) || opts.adults < 1 || opts.adults > 9) throw new Error('--adults must be an integer from 1 to 9');
  if (!Number.isInteger(opts.limit) || opts.limit < 1) throw new Error('--limit must be a positive integer');
  return opts;
}

function addDays(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

async function fetchAvailability(opts) {
  const params = new URLSearchParams({
    flightCount: '1',
    includeSoldOut: 'true',
    requestType: 'Original',
    from: opts.date,
    end: addDays(opts.date, opts.days),
    departures: opts.origin,
    arrivals: opts.destination,
    direction: 'outbound',
    paxCount: String(opts.adults),
    includeFees: 'true',
  });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(`${API}?${params}`, {
      headers: {
        accept: 'application/json',
        culture: 'en-NZ',
        origin: 'https://www.jetstar.com',
        referer: 'https://www.jetstar.com/nz/en/home',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
      },
      signal: controller.signal,
    });
    const body = await res.text();
    if (!res.ok) throw new Error(`Jetstar API returned HTTP ${res.status}: ${body.slice(0, 300)}`);
    return JSON.parse(body);
  } finally {
    clearTimeout(timer);
  }
}

function flatten(raw, opts) {
  const flights = [];
  const routeKey = `${opts.origin}${opts.destination}`.toLowerCase();
  for (const batch of raw) {
    const route = batch.routes?.[routeKey];
    const byDate = route?.flights || {};
    for (const [yyyymmdd, rows] of Object.entries(byDate)) {
      const date = `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
      for (const row of rows || []) {
        flights.push({
          airline: 'Jetstar',
          flight_id: row.flightId,
          origin: opts.origin,
          destination: opts.destination,
          date,
          departure: row.departureTime,
          arrival: row.arrivalTime,
          price: row.price,
          currency: batch.currencyCode,
          sold_out: row.soldOut,
          member: row.member,
          stops: row.stopCount,
          fare_classes: row.fareClasses || [],
        });
      }
    }
  }
  flights.sort((a, b) => `${a.departure}`.localeCompare(`${b.departure}`));
  return { source: 'jetstar.com', origin: opts.origin, destination: opts.destination, from: opts.date, days: opts.days, flights };
}

function printHuman(result, limit) {
  console.log(`Jetstar flights: ${result.flights.length} found`);
  for (const f of result.flights.slice(0, limit)) {
    const sold = f.sold_out ? ' SOLD OUT' : '';
    console.log(`- ${f.departure} → ${f.arrival} | flightId ${f.flight_id} | ${f.stops} stops | ${f.currency} $${f.price}${sold}`);
  }
}

async function main() {
  try {
    const opts = parseArgs(process.argv.slice(2));
    const raw = await fetchAvailability(opts);
    const result = flatten(raw, opts);
    if (opts.json) console.log(JSON.stringify(result, null, 2));
    else printHuman(result, opts.limit);
  } catch (err) {
    console.error(`ERROR: ${err.message}`);
    process.exit(1);
  }
}

main();
