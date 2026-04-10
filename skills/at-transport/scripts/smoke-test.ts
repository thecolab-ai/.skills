import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getServiceAlerts,
  getTripUpdates,
  getVehiclePositions,
  getStops,
  getRoutesMap,
  searchStops,
  nearbyStops,
  getDepartures,
  getNetworkStatus,
} from './client.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '../../..');
const cliPath = 'skills/at-transport/scripts/cli.ts';

function runCliJson(args: string[]) {
  const stdout = execFileSync('npx', ['tsx', cliPath, ...args, '--json'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 30_000,
  });
  return JSON.parse(stdout) as Record<string, unknown>;
}

async function main() {
  console.log('Testing AT API client functions...');

  // Service alerts
  const alerts = await getServiceAlerts();
  assert(Array.isArray(alerts), 'alerts must be an array');
  console.log(`  ✓ getServiceAlerts: ${alerts.length} alerts`);

  // Trip updates
  const tripUpdates = await getTripUpdates();
  assert(Array.isArray(tripUpdates), 'tripUpdates must be an array');
  console.log(`  ✓ getTripUpdates: ${tripUpdates.length} updates`);

  // Vehicle positions
  const vehicles = await getVehiclePositions();
  assert(Array.isArray(vehicles), 'vehicles must be an array');
  console.log(`  ✓ getVehiclePositions: ${vehicles.length} vehicles`);

  // Stops
  const stops = await getStops();
  assert(Array.isArray(stops), 'stops must be an array');
  assert(stops.length > 1000, `expected many stops, got ${stops.length}`);
  console.log(`  ✓ getStops: ${stops.length} stops`);

  // Routes
  const routes = await getRoutesMap();
  assert(routes instanceof Map, 'routes must be a Map');
  assert(routes.size > 10, `expected many routes, got ${routes.size}`);
  console.log(`  ✓ getRoutesMap: ${routes.size} routes`);

  // Search stops
  const britomartStops = await searchStops('Britomart');
  assert(britomartStops.length > 0, 'should find Britomart stops');
  console.log(`  ✓ searchStops("Britomart"): ${britomartStops.length} matches`);

  // Nearby stops (Britomart area)
  const nearby = await nearbyStops(-36.8441, 174.7679, 500);
  assert(Array.isArray(nearby), 'nearby must be an array');
  console.log(`  ✓ nearbyStops(Britomart area): ${nearby.length} stops within 500m`);

  // Departures
  const departures = await getDepartures('11814');
  assert(departures.stop, 'departures must include stop info');
  assert(Array.isArray(departures.departures), 'departures.departures must be an array');
  console.log(`  ✓ getDepartures(11814): ${departures.departures.length} departures from ${departures.stop.stop_name}`);

  // Network status
  const status = await getNetworkStatus();
  assert(typeof status.active_trips === 'number', 'status must include active_trips');
  assert(typeof status.on_time_percentage === 'number', 'status must include on_time_percentage');
  console.log(`  ✓ getNetworkStatus: ${status.active_trips} trips, ${status.on_time_percentage}% on time`);

  console.log('\nTesting CLI commands...');

  // CLI: alerts
  const alertsJson = runCliJson(['alerts']);
  assert(typeof alertsJson.total_active === 'number', 'alerts JSON must include total_active');
  console.log(`  ✓ cli alerts: ${alertsJson.total_active} active`);

  // CLI: stops
  const stopsJson = runCliJson(['stops', 'Britomart']);
  assert(typeof stopsJson.total_matches === 'number', 'stops JSON must include total_matches');
  assert((stopsJson.total_matches as number) > 0, 'should find Britomart stops');
  console.log(`  ✓ cli stops Britomart: ${stopsJson.total_matches} matches`);

  // CLI: departures
  const depsJson = runCliJson(['departures', '11814']);
  assert(typeof depsJson.total_departures === 'number', 'departures JSON must include total_departures');
  console.log(`  ✓ cli departures 11814: ${depsJson.total_departures} departures`);

  // CLI: nearby
  const nearbyJson = runCliJson(['nearby', '--location=-36.844,174.768']);
  assert(typeof nearbyJson.total_nearby === 'number', 'nearby JSON must include total_nearby');
  console.log(`  ✓ cli nearby: ${nearbyJson.total_nearby} stops`);

  // CLI: vehicles
  const vehiclesJson = runCliJson(['vehicles', '--limit', '5']);
  assert(typeof vehiclesJson.total_vehicles === 'number', 'vehicles JSON must include total_vehicles');
  console.log(`  ✓ cli vehicles: ${vehiclesJson.total_vehicles} total`);

  // CLI: status
  const statusJson = runCliJson(['status']);
  assert(typeof statusJson.active_trips === 'number', 'status JSON must include active_trips');
  console.log(`  ✓ cli status: ${statusJson.active_trips} active trips`);

  console.log('\n✅ Auckland Transport smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
