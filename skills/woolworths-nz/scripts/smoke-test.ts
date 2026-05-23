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
    throw new Error(`woolworths-nz smoke failed: python3 ${cliPath} ${args.join(' ')}
${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const searchRaw = run(['search', 'milk', '--limit', '3', '--json']);
const search = JSON.parse(searchRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(search.products) || search.products.length < 1) {
  throw new Error('Expected Woolworths search JSON to include products[]');
}
const sku = String(search.products[0].sku || '705692');
const productRaw = run(['product', sku, '--json']);
const product = JSON.parse(productRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(product.products) || product.products.length < 1 || !product.products[0].sku) {
  throw new Error('Expected Woolworths product JSON to include a SKU product');
}
const specialsRaw = run(['specials', 'cheese', '--limit', '3', '--json']);
const specials = JSON.parse(specialsRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(specials.products)) {
  throw new Error('Expected Woolworths specials JSON to include products[]');
}
console.log('woolworths-nz smoke ok');
