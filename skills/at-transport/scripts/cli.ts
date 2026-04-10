#!/usr/bin/env node
import { Command, Option } from 'commander';
import { pathToFileURL } from 'node:url';
import {
  getServiceAlerts,
  getDepartures,
  searchStops,
  nearbyStops,
  getRoute,
  getRoutesMap,
  getVehiclePositions,
  getNetworkStatus,
  routeTypeIcon,
  routeTypeName,
  type ServiceAlert,
  type Departure,
  type Stop,
  type Route,
  type VehiclePosition,
  type NetworkStatus,
} from './client.js';

type JsonFlag = { json?: boolean };

const program = new Command();

const nzFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

const nzFullFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZoneName: 'short',
});

function printOutput(data: unknown, json: boolean | undefined, render: () => string) {
  if (json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }
  console.log(render());
}

function formatTime(isoOrTimestamp: string | number | null): string {
  if (!isoOrTimestamp) return '??:??';
  const date = typeof isoOrTimestamp === 'number' ? new Date(isoOrTimestamp * 1000) : new Date(isoOrTimestamp);
  if (Number.isNaN(date.getTime())) return String(isoOrTimestamp);
  return nzFormatter.format(date);
}

function formatFullTime(isoOrTimestamp: string | number | null): string {
  if (!isoOrTimestamp) return 'unknown';
  const date = typeof isoOrTimestamp === 'number' ? new Date(isoOrTimestamp * 1000) : new Date(isoOrTimestamp);
  if (Number.isNaN(date.getTime())) return String(isoOrTimestamp);
  return nzFullFormatter.format(date);
}

function formatDelay(seconds: number): string {
  if (Math.abs(seconds) <= 60) return '(on time)';
  const mins = Math.round(seconds / 60);
  if (mins > 0) return `(+${mins} min late)`;
  return `(${Math.abs(mins)} min early)`;
}

function formatDistance(meters: number): string {
  if (meters < 1000) return `${meters}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}

function parsePositiveInt(raw: string): number {
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`Expected a positive integer, received: ${raw}`);
  }
  return value;
}

function parseLatLon(raw: string): { lat: number; lon: number } {
  const parts = raw.split(',').map((s) => Number.parseFloat(s.trim()));
  if (parts.length !== 2 || parts.some(Number.isNaN)) {
    throw new Error(`Expected lat,lon format (e.g. -36.844,174.768), received: ${raw}`);
  }
  return { lat: parts[0], lon: parts[1] };
}

function severityLabel(level: string): string {
  switch (level) {
    case 'SEVERE': return 'MAJOR';
    case 'WARNING': return 'WARN';
    case 'INFO': return 'INFO';
    default: return level;
  }
}

function addExamples(command: Command, examples: string[]): Command {
  return command.addHelpText(
    'after',
    `\nExamples:\n${examples.map((e) => `  ${e}`).join('\n')}`,
  );
}

// --- Commands ---

program
  .name('at-transport')
  .description('Query live Auckland Transport public transport data — stops, departures, alerts, vehicles, and network status.')
  .showHelpAfterError('(add --help for usage)');

addExamples(program, [
  'npx tsx skills/at-transport/scripts/cli.ts alerts',
  'npx tsx skills/at-transport/scripts/cli.ts departures 11814',
  'npx tsx skills/at-transport/scripts/cli.ts stops Britomart',
  'npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768',
  'npx tsx skills/at-transport/scripts/cli.ts route STH-201',
  'npx tsx skills/at-transport/scripts/cli.ts vehicles --route STH-201',
  'npx tsx skills/at-transport/scripts/cli.ts status',
]);

// --- alerts ---

addExamples(
  program
    .command('alerts')
    .description('Show active service alerts and disruptions.')
    .option('--limit <n>', 'limit number of alerts', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { limit?: number }) => {
      const alerts = await getServiceAlerts();
      const now = Date.now() / 1000;
      const active = alerts.filter((a) =>
        a.active_period.some((p) => p.start <= now && now <= p.end),
      );
      const limited = options.limit ? active.slice(0, options.limit) : active;

      const output = {
        timestamp: new Date().toISOString(),
        total_active: active.length,
        returned: limited.length,
        alerts: limited,
      };

      printOutput(output, options.json, () => {
        if (active.length === 0) return 'No active service alerts.';
        const lines = [`⚠️  SERVICE ALERTS (${active.length} active)`];
        for (const a of limited) {
          lines.push(`  [${severityLabel(a.severity_level)}] ${a.header_text}`);
          if (a.description_text) {
            const desc = a.description_text.length > 200
              ? a.description_text.slice(0, 200) + '...'
              : a.description_text;
            lines.push(`         ${desc.replace(/\n/g, '\n         ')}`);
          }
        }
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts alerts',
    'npx tsx skills/at-transport/scripts/cli.ts alerts --limit 5',
    'npx tsx skills/at-transport/scripts/cli.ts alerts --json',
  ],
);

// --- departures ---

addExamples(
  program
    .command('departures')
    .description('Show next departures from a stop (real-time). Use stop code or stop ID.')
    .argument('<stop_id>', 'stop code (e.g. 11814) or full stop ID')
    .option('--limit <n>', 'limit departures shown (default 15)', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (stopId: string, options: JsonFlag & { limit?: number }) => {
      const limit = options.limit ?? 15;
      const result = await getDepartures(stopId);
      const departures = result.departures.slice(0, limit);

      const output = {
        stop: result.stop,
        total_departures: result.departures.length,
        returned: departures.length,
        departures,
      };

      printOutput(output, options.json, () => {
        const lines = [
          `${routeTypeIcon(3)} Departures from ${result.stop.stop_name} (Stop ${result.stop.stop_code})`,
          '──────────────────────────────────────────',
        ];

        if (departures.length === 0) {
          lines.push('  No real-time departures currently tracked for this stop.');
          lines.push('  This may be because no vehicles are currently approaching this stop.');
          return lines.join('\n');
        }

        for (const d of departures) {
          const icon = routeTypeIcon(d.route_type);
          const time = d.expected_time ? formatTime(d.expected_time) : d.scheduled_time;
          const delay = formatDelay(d.delay_seconds);
          const routeName = d.route_short_name;
          lines.push(`  ${icon} Route ${routeName.padEnd(6)} Due ${time.padEnd(10)} ${delay}`);
        }

        lines.push('');
        lines.push(`  ${result.departures.length} total departures tracked`);
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts departures 11814',
    'npx tsx skills/at-transport/scripts/cli.ts departures 7155 --limit 5',
    'npx tsx skills/at-transport/scripts/cli.ts departures 11814 --json',
  ],
);

// --- stops ---

addExamples(
  program
    .command('stops')
    .description('Search for stops by name or code.')
    .argument('<query>', 'search term (stop name, code, or ID)')
    .option('--limit <n>', 'limit results (default 20)', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (query: string, options: JsonFlag & { limit?: number }) => {
      const limit = options.limit ?? 20;
      const results = await searchStops(query);
      const limited = results.slice(0, limit);

      const output = {
        query,
        total_matches: results.length,
        returned: limited.length,
        stops: limited,
      };

      printOutput(output, options.json, () => {
        if (results.length === 0) return `No stops found matching "${query}".`;

        const lines = [`🔍 Stops matching "${query}" (${results.length} found)`];
        lines.push('──────────────────────────────────────────');

        for (const s of limited) {
          const type = s.location_type === 1 ? ' [Station]' : '';
          const platform = s.platform_code ? ` (Platform ${s.platform_code})` : '';
          lines.push(`  ${s.stop_code.padEnd(8)} ${s.stop_name}${type}${platform}`);
          lines.push(`           ID: ${s.stop_id}  (${s.stop_lat.toFixed(5)}, ${s.stop_lon.toFixed(5)})`);
        }

        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts stops Britomart',
    'npx tsx skills/at-transport/scripts/cli.ts stops Newmarket',
    'npx tsx skills/at-transport/scripts/cli.ts stops 7155 --json',
  ],
);

// --- nearby ---

addExamples(
  program
    .command('nearby')
    .description('Find stops near a location.')
    .requiredOption('--location <lat,lon>', 'latitude,longitude (e.g. --location=-36.844,174.768)', parseLatLon)
    .option('--radius <meters>', 'search radius in meters (default 500)', parsePositiveInt)
    .option('--limit <n>', 'limit results (default 20)', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { location: { lat: number; lon: number }; radius?: number; limit?: number }) => {
      const { lat, lon } = options.location;
      const radius = options.radius ?? 500;
      const limit = options.limit ?? 20;
      const results = await nearbyStops(lat, lon, radius);
      const limited = results.slice(0, limit);

      const output = {
        location: { lat, lon },
        radius_m: radius,
        total_nearby: results.length,
        returned: limited.length,
        stops: limited,
      };

      printOutput(output, options.json, () => {
        if (results.length === 0) return `No stops found within ${radius}m of ${lat},${lon}.`;

        const lines = [`📍 Stops within ${formatDistance(radius)} of ${lat.toFixed(5)},${lon.toFixed(5)} (${results.length} found)`];
        lines.push('──────────────────────────────────────────');

        for (const s of limited) {
          const type = s.location_type === 1 ? ' [Station]' : '';
          lines.push(`  ${formatDistance(s.distance_m).padEnd(6)} ${s.stop_code.padEnd(8)} ${s.stop_name}${type}`);
        }

        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768',
    'npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768 --radius 1000',
    'npx tsx skills/at-transport/scripts/cli.ts nearby --location=-36.844,174.768 --json',
  ],
);

// --- route ---

addExamples(
  program
    .command('route')
    .description('Show info about a specific route.')
    .argument('<route_id>', 'route ID (e.g. STH-201, 70-221)')
    .option('--json', 'emit machine-readable JSON')
    .action(async (routeId: string, options: JsonFlag) => {
      let route: Route;
      try {
        route = await getRoute(routeId);
      } catch {
        // Try searching by short name
        const routesMap = await getRoutesMap();
        const match = [...routesMap.values()].find(
          (r) => r.route_short_name.toLowerCase() === routeId.toLowerCase(),
        );
        if (!match) throw new Error(`Route not found: ${routeId}. Use the full route ID (e.g. STH-201).`);
        route = match;
      }

      printOutput(route, options.json, () => {
        const lines = [
          `${routeTypeIcon(route.route_type)} Route ${route.route_short_name}`,
          '──────────────────────────────────────────',
          `  ID:       ${route.route_id}`,
          `  Name:     ${route.route_long_name}`,
          `  Type:     ${routeTypeName(route.route_type)}`,
          `  Agency:   ${route.agency_id}`,
        ];
        if (route.route_color) lines.push(`  Color:    #${route.route_color}`);
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts route STH-201',
    'npx tsx skills/at-transport/scripts/cli.ts route 70-221 --json',
  ],
);

// --- vehicles ---

addExamples(
  program
    .command('vehicles')
    .description('Show live vehicle positions, optionally filtered by route.')
    .option('--route <route_id>', 'filter by route ID')
    .option('--limit <n>', 'limit results (default 20)', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { route?: string; limit?: number }) => {
      const limit = options.limit ?? 20;
      let vehicles = await getVehiclePositions();

      if (options.route) {
        vehicles = vehicles.filter((v) => v.trip?.route_id === options.route);
      }

      // Sort by most recently updated
      vehicles.sort((a, b) => b.timestamp - a.timestamp);
      const limited = vehicles.slice(0, limit);

      const output = {
        timestamp: new Date().toISOString(),
        filter_route: options.route ?? null,
        total_vehicles: vehicles.length,
        returned: limited.length,
        vehicles: limited.map((v) => ({
          vehicle_id: v.id,
          label: v.vehicle.label,
          lat: v.position.latitude,
          lon: v.position.longitude,
          speed: v.position.speed,
          bearing: v.position.bearing ?? null,
          route_id: v.trip?.route_id ?? null,
          trip_id: v.trip?.trip_id ?? null,
          last_update: new Date(v.timestamp * 1000).toISOString(),
        })),
      };

      printOutput(output, options.json, () => {
        const routeLabel = options.route ? ` on route ${options.route}` : '';
        const lines = [`🚍 Live vehicles${routeLabel} (${vehicles.length} total)`];
        lines.push('──────────────────────────────────────────');

        if (limited.length === 0) {
          lines.push('  No vehicles currently tracked.');
          return lines.join('\n');
        }

        for (const v of limited) {
          const route = v.trip?.route_id ?? 'unknown';
          const speed = v.position.speed > 0 ? `${(v.position.speed * 3.6).toFixed(0)} km/h` : 'stopped';
          const label = v.vehicle.label?.trim() || v.id;
          lines.push(
            `  ${label.padEnd(18)} Route ${route.padEnd(10)} ${speed.padEnd(10)} (${v.position.latitude.toFixed(4)}, ${v.position.longitude.toFixed(4)})`,
          );
        }

        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts vehicles',
    'npx tsx skills/at-transport/scripts/cli.ts vehicles --route STH-201',
    'npx tsx skills/at-transport/scripts/cli.ts vehicles --limit 10 --json',
  ],
);

// --- status ---

addExamples(
  program
    .command('status')
    .description('Show overall Auckland Transport network status summary.')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag) => {
      const status = await getNetworkStatus();

      printOutput(status, options.json, () => {
        const lines = [
          `🚦 Auckland Transport Network Status`,
          `   ${formatFullTime(status.timestamp)}`,
          '──────────────────────────────────────────',
          `  Active trips:     ${status.active_trips}`,
          `  Active vehicles:  ${status.active_vehicles}`,
          `  On-time:          ${status.on_time_percentage}%`,
          `  Delayed trips:    ${status.delayed_trips}`,
          `  Avg delay:        ${status.avg_delay_seconds}s`,
          `  Service alerts:   ${status.alerts_count}`,
        ];

        if (Object.keys(status.alerts_by_severity).length > 0) {
          const sevParts = Object.entries(status.alerts_by_severity)
            .map(([k, v]) => `${severityLabel(k)}: ${v}`)
            .join(', ');
          lines.push(`  Alert breakdown:  ${sevParts}`);
        }

        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/at-transport/scripts/cli.ts status',
    'npx tsx skills/at-transport/scripts/cli.ts status --json',
  ],
);

async function main() {
  await program.parseAsync(process.argv);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
