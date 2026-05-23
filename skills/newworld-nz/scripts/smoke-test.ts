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
    timeout: 30_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`newworld smoke failed: python3 ${cliPath} ${args.join(' ')}\n${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const storesRaw = run(['stores', '--query', 'papakura', '--limit', '1', '--json']);
const stores = JSON.parse(storesRaw) as Array<Record<string, unknown>>;
if (!Array.isArray(stores) || stores.length < 1) {
  throw new Error('Expected at least one New World store for Papakura');
}

const searchRaw = run(['search', 'milk', '--limit', '1', '--json']);
const search = JSON.parse(searchRaw) as Record<string, unknown>;
if (!Array.isArray(search.products)) {
  throw new Error('Expected New World search JSON to include products[]');
}

console.log('newworld-nz smoke ok');
