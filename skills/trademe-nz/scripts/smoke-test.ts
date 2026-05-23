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
    throw new Error(`trademe-nz smoke failed: python3 ${cliPath} ${args.join(' ')}
${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const marketplaceRaw = run(['search', 'iphone', '--limit', '3', '--json']);
const marketplace = JSON.parse(marketplaceRaw) as { listings?: Array<Record<string, unknown>> };
if (!Array.isArray(marketplace.listings) || marketplace.listings.length < 1) {
  throw new Error('Expected Trade Me marketplace search JSON to include listings[]');
}
const listingId = String(marketplace.listings[0].listing_id);
const listingRaw = run(['listing', listingId, '--json']);
const listing = JSON.parse(listingRaw) as { listing?: Record<string, unknown> };
if (!listing.listing?.listing_id) {
  throw new Error('Expected Trade Me listing JSON to include listing.listing_id');
}
const propertyRaw = run(['search', 'auckland', '--type', 'property-rent', '--region', 'auckland', '--bedrooms-min', '2', '--price-max', '800', '--limit', '3', '--json']);
const property = JSON.parse(propertyRaw) as { listings?: Array<Record<string, unknown>> };
if (!Array.isArray(property.listings)) {
  throw new Error('Expected Trade Me property-rent search JSON to include listings[]');
}
const motorsRaw = run(['search', 'aqua', '--type', 'motors', '--region', 'auckland', '--price-max', '15000', '--limit', '3', '--json']);
const motors = JSON.parse(motorsRaw) as { listings?: Array<Record<string, unknown>> };
if (!Array.isArray(motors.listings)) {
  throw new Error('Expected Trade Me motors search JSON to include listings[]');
}
const regionsRaw = run(['regions', '--json']);
const regions = JSON.parse(regionsRaw) as { regions?: Array<Record<string, unknown>> };
if (!Array.isArray(regions.regions) || regions.regions.length < 1) {
  throw new Error('Expected Trade Me regions JSON to include regions[]');
}
console.log('trademe-nz smoke ok');
