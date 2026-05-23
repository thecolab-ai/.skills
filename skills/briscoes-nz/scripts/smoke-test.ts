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
    throw new Error(`briscoes-nz smoke failed: python3 ${cliPath} ${args.join(' ')}
${result.stderr || result.stdout}`);
  }
  return result.stdout;
}

run(['--help']);
const searchRaw = run(['search', 'towel', '--limit', '3', '--json']);
const search = JSON.parse(searchRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(search.products) || search.products.length < 1) {
  throw new Error('Expected Briscoes search JSON to include products[]');
}
const sku = String(search.products[0].sku || '1129433');
const productRaw = run(['product', sku, '--json']);
const product = JSON.parse(productRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(product.products) || product.products.length < 1 || !product.products[0].sku) {
  throw new Error('Expected Briscoes product JSON to include a SKU product');
}
const storesRaw = run(['stores', '--region', 'auckland', '--json']);
const stores = JSON.parse(storesRaw) as { stores?: Array<Record<string, unknown>> };
if (!Array.isArray(stores.stores) || stores.stores.length < 1) {
  throw new Error('Expected Briscoes stores JSON to include Auckland stores[]');
}
const wellingtonStoresRaw = run(['stores', '--region', 'wellington', '--json']);
const wellingtonStores = JSON.parse(wellingtonStoresRaw) as { stores?: Array<Record<string, unknown>> };
if (!Array.isArray(wellingtonStores.stores) || wellingtonStores.stores.some((store) => String(store.city || '').toLowerCase() === 'auckland')) {
  throw new Error('Expected Wellington store filter not to include Auckland street-address matches');
}
const specialsRaw = run(['specials', 'towel', '--limit', '3', '--json']);
const specials = JSON.parse(specialsRaw) as { products?: Array<Record<string, unknown>> };
if (!Array.isArray(specials.products)) {
  throw new Error('Expected Briscoes specials JSON to include products[]');
}
for (const product of specials.products) {
  const price = Number(product.price);
  const salePrice = Number(product.sale_price);
  const savePrice = Number(product.save_price);
  if (!(Number.isFinite(price) && Number.isFinite(salePrice) && salePrice < price && savePrice > 0)) {
    throw new Error('Expected every Briscoes specials product to have a verified discount');
  }
  const haystack = `${product.name || ''} ${product.category || ''} ${product.source_url || ''}`.toLowerCase();
  if (!haystack.includes('towel')) {
    throw new Error('Expected Briscoes specials towel query to constrain returned products');
  }
}
console.log('briscoes-nz smoke ok');
