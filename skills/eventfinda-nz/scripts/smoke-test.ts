#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliPath = resolve(__dirname, 'cli.py');

function run(args: string[]) {
  const result = spawnSync('python3', [cliPath, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 60_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`eventfinda-nz smoke failed: python3 ${cliPath} ${args.join(' ')}\n${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const upcomingRaw = run(['upcoming', '--location', 'auckland', '--limit', '3', '--json']);
const upcoming = JSON.parse(upcomingRaw) as { events?: Array<Record<string, unknown>> };
if (!Array.isArray(upcoming.events) || upcoming.events.length < 1) {
  throw new Error('Expected upcoming JSON to include events[]');
}
const first = upcoming.events[0];
if (typeof first.title !== 'string' || typeof first.url !== 'string') {
  throw new Error('Expected first upcoming event to include title and url');
}
const searchRaw = run(['search', 'music', '--limit', '3', '--json']);
const search = JSON.parse(searchRaw) as { events?: Array<Record<string, unknown>> };
if (!Array.isArray(search.events)) {
  throw new Error('Expected search JSON to include events[]');
}
const detailRaw = run(['event', String(first.url), '--json']);
const detail = JSON.parse(detailRaw) as { event?: Record<string, unknown> };
if (!detail.event?.title || !Array.isArray(detail.event.sessions)) {
  throw new Error('Expected event detail JSON to include title and sessions[]');
}
console.log('eventfinda-nz smoke ok');
