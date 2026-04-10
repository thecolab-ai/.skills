import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getGeopoliticalRisk,
  getNews,
} from './client.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '../../..');
const cliPath = 'skills/fuelclock-nz-watch/scripts/cli.ts';

function runCliJson(args: string[]) {
  const stdout = execFileSync('npx', ['tsx', cliPath, ...args, '--json'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  return JSON.parse(stdout) as Record<string, unknown>;
}

async function main() {
  const risk = await getGeopoliticalRisk();
  assert(Array.isArray(risk.markets), 'risk.markets must be an array');

  const news = await getNews();
  assert(Array.isArray(news.articles), 'news.articles must be an array');

  const summaryJson = runCliJson(['summary']);
  assert(typeof summaryJson === 'object', 'summary JSON must parse');
  assert('risk' in summaryJson, 'summary JSON must include risk');
  assert('news' in summaryJson, 'summary JSON must include news');

  const riskJson = runCliJson(['risk', '--limit', '2']);
  assert(riskJson.returnedCount === 2, 'risk --limit 2 should return two rows');

  const newsJson = runCliJson(['news', '--limit', '2']);
  assert(newsJson.returnedCount === 2, 'news --limit 2 should return two rows');

  console.log('FuelClock NZ Watch smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
