import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  FEEDS,
  PRIMARY_FEED_IDS,
  fetchFeed,
  fetchFeeds,
  deduplicateItems,
  sortByDate,
  filterByKeyword,
} from './feeds.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '../../..');
const cliPath = 'skills/nz-news/scripts/cli.ts';

function runCliJson(args: string[]) {
  const stdout = execFileSync('npx', ['tsx', cliPath, ...args, '--json'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  return JSON.parse(stdout) as Record<string, unknown>;
}

async function main() {
  console.log('Testing feed library...');

  // Test individual feed fetch (RNZ is reliable)
  const rnzFeed = FEEDS.find((f) => f.id === 'rnz')!;
  const rnzResult = await fetchFeed(rnzFeed);
  assert(rnzResult.ok, `RNZ feed should succeed, got: ${rnzResult.error}`);
  assert(rnzResult.items.length > 0, 'RNZ feed should return items');
  assert(rnzResult.items[0].title.length > 0, 'RNZ items should have titles');
  assert(rnzResult.items[0].url.startsWith('http'), 'RNZ items should have URLs');
  console.log(`  ✓ RNZ feed: ${rnzResult.items.length} items`);

  // Test primary feeds
  const primaryResults = await fetchFeeds();
  const okCount = primaryResults.filter((r) => r.ok).length;
  assert(okCount >= 3, `At least 3 primary feeds should work, got ${okCount}`);
  console.log(`  ✓ Primary feeds: ${okCount}/${primaryResults.length} ok`);

  // Test deduplication
  const allItems = primaryResults.flatMap((r) => r.items);
  const deduped = deduplicateItems(allItems);
  assert(deduped.length <= allItems.length, 'Deduplicated count should be <= total');
  assert(deduped.length > 0, 'Should have items after dedup');
  console.log(`  ✓ Dedup: ${allItems.length} → ${deduped.length} items`);

  // Test sort
  const sorted = sortByDate(deduped);
  assert(sorted[0].published >= sorted[sorted.length - 1].published, 'Should be sorted newest first');
  console.log('  ✓ Sort: newest first');

  // Test keyword filter
  const filtered = filterByKeyword(allItems, 'new zealand');
  console.log(`  ✓ Keyword filter "new zealand": ${filtered.length} matches`);

  console.log('\nTesting CLI commands...');

  // Test headlines
  const headlinesJson = runCliJson(['headlines', '--limit', '5']);
  assert(typeof headlinesJson.sourcesOk === 'number', 'headlines JSON must include sourcesOk');
  assert(Array.isArray(headlinesJson.items), 'headlines JSON must include items array');
  assert((headlinesJson.items as unknown[]).length <= 5, 'headlines should respect --limit');
  console.log(`  ✓ headlines --limit 5: ${(headlinesJson.items as unknown[]).length} items`);

  // Test source
  const sourceJson = runCliJson(['source', 'rnz', '--limit', '3']);
  assert(sourceJson.sourceId === 'rnz', 'source should return rnz');
  assert(Array.isArray(sourceJson.items), 'source JSON must include items array');
  console.log(`  ✓ source rnz --limit 3: ${(sourceJson.items as unknown[]).length} items`);

  // Test sources
  const sourcesJson = runCliJson(['sources']);
  assert(typeof sourcesJson.working === 'number', 'sources JSON must include working count');
  assert(Array.isArray(sourcesJson.sources), 'sources JSON must include sources array');
  console.log(`  ✓ sources: ${sourcesJson.working}/${sourcesJson.totalSources} working`);

  // Test summary
  const summaryJson = runCliJson(['summary']);
  assert(typeof summaryJson.totalStories === 'number', 'summary JSON must include totalStories');
  assert(Array.isArray(summaryJson.top5), 'summary JSON must include top5 array');
  console.log(`  ✓ summary: ${summaryJson.totalStories} stories, ${(summaryJson.top5 as unknown[]).length} top headlines`);

  // Test topic
  const topicJson = runCliJson(['topic', 'zealand']);
  assert(typeof topicJson.totalMatching === 'number', 'topic JSON must include totalMatching');
  console.log(`  ✓ topic "zealand": ${topicJson.totalMatching} matches`);

  console.log('\nNZ News smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
