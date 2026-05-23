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
    timeout: 45_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`auckland-bin-schedule smoke failed: python3 ${cliPath} ${args.join(' ')}
${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const listRaw = run(['--list', '12 Tawa Road Onehunga', '--limit', '3', '--json']);
const list = JSON.parse(listRaw) as { matches?: Array<Record<string, unknown>> };
if (!Array.isArray(list.matches) || list.matches.length < 1) {
  throw new Error('Expected at least one Auckland Council property match for 12 Tawa Road Onehunga');
}

const scheduleRaw = run(['12 Tawa Road Onehunga', '--json']);
const schedule = JSON.parse(scheduleRaw) as Record<string, unknown>;
if (!schedule.property_id || !schedule.household) {
  throw new Error('Expected schedule JSON to include property_id and household collection data');
}

console.log('auckland-bin-schedule smoke ok');
