import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  LOCATIONS,
  resolveLocation,
  fetchCurrentConditions,
  fetchHourlyForecast,
  fetchDailyForecast,
  fetchMarineForecast,
  fetchWindForecast,
  fetchRainForecast,
  fetchCycloneData,
  fetchPressureTrend,
  scrapeWarnings,
} from './client.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '../../..');
const cliPath = 'skills/metservice-nz/scripts/cli.ts';

function runCliJson(args: string[]) {
  const stdout = execFileSync('npx', ['tsx', cliPath, ...args, '--json'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 30_000,
  });

  return JSON.parse(stdout) as Record<string, unknown>;
}

function runCliFails(args: string[]): boolean {
  try {
    execFileSync('npx', ['tsx', cliPath, ...args], {
      cwd: repoRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 15_000,
    });
    return false;
  } catch {
    return true;
  }
}

async function main() {
  console.log('Testing MetOcean API client functions...');

  // Test resolveLocation
  const resolved = resolveLocation('auckland');
  assert(resolved.name === 'Auckland CBD', 'resolveLocation should find auckland');
  const custom = resolveLocation(undefined, '-37.0,175.5');
  assert(custom.lat === -37.0, 'resolveLocation should parse custom coords');
  // No-location should throw
  let threw = false;
  try { resolveLocation(); } catch { threw = true; }
  assert(threw, 'resolveLocation with no args must throw');
  console.log('  resolveLocation: OK');

  // Test with Auckland
  const auckland = LOCATIONS.auckland;
  console.log(`\nTesting API functions with ${auckland.name}...`);

  const current = await fetchCurrentConditions(auckland);
  assert(current.tempC !== null, 'current temp must not be null');
  assert(typeof current.tempC === 'number', 'current temp must be a number');
  assert(current.tempC > -20 && current.tempC < 50, `current temp ${current.tempC}°C out of reasonable range`);
  assert(current.windSpeedKmh !== null, 'current wind must not be null');
  console.log(`  fetchCurrentConditions: OK (${current.tempC.toFixed(1)}°C, ${current.windSpeedKmh?.toFixed(0)} km/h wind)`);

  const hourly = await fetchHourlyForecast(auckland);
  assert(hourly.hours.length > 20, `hourly should have 24+ entries, got ${hourly.hours.length}`);
  assert(hourly.hours[0].tempC !== null, 'hourly first entry must have temp');
  console.log(`  fetchHourlyForecast: OK (${hourly.hours.length} hours)`);

  const daily = await fetchDailyForecast(auckland);
  assert(daily.days.length >= 6, `daily should have 7+ days, got ${daily.days.length}`);
  assert(daily.days[0].highC !== null, 'daily first day must have high temp');
  console.log(`  fetchDailyForecast: OK (${daily.days.length} days)`);

  const marine = await fetchMarineForecast(auckland);
  assert(marine.hours.length > 20, `marine should have 24+ entries, got ${marine.hours.length}`);
  console.log(`  fetchMarineForecast: OK (${marine.hours.length} hours, wave data: ${marine.hours[0].waveHeightM !== null ? 'yes' : 'no'})`);

  const wind = await fetchWindForecast(auckland);
  assert(wind.hours.length > 20, `wind should have 24+ entries, got ${wind.hours.length}`);
  assert(wind.hours[0].speedKmh !== null, 'wind first entry must have speed');
  console.log(`  fetchWindForecast: OK (${wind.hours.length} hours)`);

  const rain = await fetchRainForecast(auckland);
  assert(rain.hours.length > 20, `rain should have 24+ entries, got ${rain.hours.length}`);
  console.log(`  fetchRainForecast: OK (${rain.hours.length} hours)`);

  const cyclone = await fetchCycloneData(auckland, 12);
  assert(cyclone.hours.length > 10, `cyclone should have 12+ entries, got ${cyclone.hours.length}`);
  assert(cyclone.pressureHpa !== null, 'cyclone must have pressure');
  assert(cyclone.windSpeedKmh !== null, 'cyclone must have wind speed');
  console.log(`  fetchCycloneData: OK (${cyclone.hours.length} hours, ${cyclone.pressureHpa?.toFixed(1)} hPa)`);

  const pressure = await fetchPressureTrend(auckland);
  assert(pressure.currentHpa !== null, 'pressure trend must have current reading');
  assert(pressure.readings.length > 20, `pressure should have 24 readings, got ${pressure.readings.length}`);
  assert(pressure.trend.direction !== 'unknown', 'pressure trend direction should be classified');
  console.log(`  fetchPressureTrend: OK (${pressure.currentHpa?.toFixed(1)} hPa, ${pressure.trend.direction})`);

  // Test with Wellington as second location
  const wellington = LOCATIONS.wellington;
  console.log(`\nTesting API functions with ${wellington.name}...`);

  const wCurrent = await fetchCurrentConditions(wellington);
  assert(wCurrent.tempC !== null, 'wellington current temp must not be null');
  console.log(`  fetchCurrentConditions: OK (${wCurrent.tempC!.toFixed(1)}°C)`);

  const wWind = await fetchWindForecast(wellington);
  assert(wWind.hours.length > 20, 'wellington wind should have 24+ entries');
  console.log(`  fetchWindForecast: OK (${wWind.hours.length} hours)`);

  // Test warnings (no location needed)
  console.log('\nTesting warnings scraper...');
  const warnings = await scrapeWarnings();
  assert(typeof warnings.source === 'string', 'warnings must have source');
  assert(typeof warnings.fetchedAt === 'string', 'warnings must have fetchedAt');
  assert(Array.isArray(warnings.warnings), 'warnings must have warnings array');
  console.log(`  scrapeWarnings: OK (${warnings.warnings.length} warnings found)`);

  // --- CLI tests ---
  console.log('\nTesting CLI commands (auckland)...');

  const nowJson = runCliJson(['now', 'auckland']);
  assert(typeof nowJson.tempC === 'number', 'now JSON must have tempC');
  console.log('  CLI now auckland: OK');

  const forecastJson = runCliJson(['forecast', 'auckland']);
  assert(Array.isArray(forecastJson.hours), 'forecast JSON must have hours array');
  console.log('  CLI forecast auckland: OK');

  const dailyJson = runCliJson(['daily', 'auckland']);
  assert(Array.isArray(dailyJson.days), 'daily JSON must have days array');
  console.log('  CLI daily auckland: OK');

  const marineJson = runCliJson(['marine', 'auckland']);
  assert(Array.isArray(marineJson.hours), 'marine JSON must have hours array');
  console.log('  CLI marine auckland: OK');

  const windJson = runCliJson(['wind', 'auckland']);
  assert(Array.isArray(windJson.hours), 'wind JSON must have hours array');
  console.log('  CLI wind auckland: OK');

  const rainJson = runCliJson(['rain', 'auckland']);
  assert(Array.isArray(rainJson.hours), 'rain JSON must have hours array');
  console.log('  CLI rain auckland: OK');

  const locsJson = runCliJson(['locations']);
  assert(Array.isArray(locsJson), 'locations JSON must be an array');
  console.log('  CLI locations: OK');

  const warningsJson = runCliJson(['warnings']);
  assert(typeof warningsJson.source === 'string', 'warnings JSON must have source');
  assert(Array.isArray(warningsJson.warnings), 'warnings JSON must have warnings array');
  console.log('  CLI warnings: OK');

  console.log('\nTesting CLI commands (wellington)...');

  const wNowJson = runCliJson(['now', 'wellington']);
  assert(typeof wNowJson.tempC === 'number', 'now wellington JSON must have tempC');
  console.log('  CLI now wellington: OK');

  const cycloneJson = runCliJson(['cyclone', 'wellington']);
  assert(Array.isArray(cycloneJson.hours), 'cyclone JSON must have hours array');
  assert(typeof cycloneJson.pressureHpa === 'number', 'cyclone JSON must have pressureHpa');
  console.log('  CLI cyclone wellington: OK');

  const pressureJson = runCliJson(['pressure', 'wellington']);
  assert(typeof pressureJson.currentHpa === 'number', 'pressure JSON must have currentHpa');
  assert(typeof (pressureJson as any).trend === 'object', 'pressure JSON must have trend object');
  console.log('  CLI pressure wellington: OK');

  // Test that no-location commands fail
  console.log('\nTesting no-location errors...');
  assert(runCliFails(['now']), 'CLI now with no location must fail');
  assert(runCliFails(['forecast']), 'CLI forecast with no location must fail');
  assert(runCliFails(['cyclone']), 'CLI cyclone with no location must fail');
  console.log('  No-location errors: OK');

  console.log('\nMetService NZ smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
