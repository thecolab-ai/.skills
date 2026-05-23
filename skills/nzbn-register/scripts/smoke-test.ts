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
    throw new Error(`nzbn-register smoke failed: python3 ${cliPath} ${args.join(' ')}\n${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const searchRaw = run(['search', 'the warehouse', '--limit', '3', '--json']);
const search = JSON.parse(searchRaw) as { entities?: Array<Record<string, unknown>>; total_items?: number };
if (!Array.isArray(search.entities) || search.entities.length < 1) {
  throw new Error('Expected NZBN search JSON to include entities[]');
}
if (typeof search.entities[0].nzbn !== 'string') {
  throw new Error('Expected first NZBN search result to include nzbn');
}
const nzbn = String(search.entities[0].nzbn);
const lookupRaw = run(['lookup', nzbn, '--json']);
const lookup = JSON.parse(lookupRaw) as { entity?: Record<string, unknown> };
if (!lookup.entity?.nzbn || lookup.entity.nzbn !== nzbn) {
  throw new Error('Expected NZBN lookup JSON to include matching entity.nzbn');
}
if (!lookup.entity.entity_name) {
  throw new Error('Expected NZBN lookup JSON to include entity.entity_name');
}
console.log('nzbn-register smoke ok');
