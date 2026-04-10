import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getFuelPrices,
  getSupplyStatus,
  getMbieStocks,
  getVessels,
} from './client.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '../../..');
const cliPath = 'skills/fuelclock-nz/scripts/cli.ts';

function runCliJson(args: string[]) {
  const stdout = execFileSync('npx', ['tsx', cliPath, ...args, '--json'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  return JSON.parse(stdout) as Record<string, unknown>;
}

async function main() {
  const prices = await getFuelPrices();
  assert(Array.isArray(prices.prices), 'prices.prices must be an array');

  const supply = await getSupplyStatus();
  assert(Array.isArray(supply.fuelStates), 'supply.fuelStates must be an array');
  assert(typeof supply.overallRisk === 'string', 'supply.overallRisk must be a string');

  const mbie = await getMbieStocks();
  assert(typeof mbie.asAtDate === 'string', 'mbie.asAtDate must be a string');

  const vessels = await getVessels();
  assert(Array.isArray(vessels.vessels), 'vessels.vessels must be an array');

  const summaryJson = runCliJson(['summary']);
  assert(typeof summaryJson === 'object', 'summary JSON must parse');
  assert('prices' in summaryJson, 'summary JSON must include prices');
  assert('supply' in summaryJson, 'summary JSON must include supply');
  assert('vessels' in summaryJson, 'summary JSON must include vessels');

  const pricesJson = runCliJson(['prices', '--fuel', 'diesel']);
  assert(pricesJson.count === 1, 'prices --fuel diesel should return one row');

  const supplyJson = runCliJson(['supply', '--below-mso']);
  assert(typeof supplyJson.count === 'number', 'supply JSON must include count');

  const vesselsJson = runCliJson(['vessels', '--flagged-only', '--limit', '2']);
  assert(typeof vesselsJson.returnedCount === 'number', 'vessels JSON must include returnedCount');

  console.log('FuelClock NZ smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
