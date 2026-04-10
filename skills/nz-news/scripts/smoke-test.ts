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
  type NewsItem,
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

function getSearchCase(items: NewsItem[]) {
  const candidate = items.find((item) => {
    if (!PRIMARY_FEED_IDS.includes(item.sourceId)) return false;
    if (item.published.getTime() === 0) return false;
    const words = item.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .split(' ')
      .filter((word) => word.length >= 4);
    return words.length >= 2;
  });

  assert(candidate, 'Expected at least one usable live item for search tests');

  const words = candidate.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .split(' ')
    .filter((word) => word.length >= 4);

  return {
    item: candidate,
    singleWord: words[0],
    phrase: `${words[0]} ${words[1]}`,
    sinceDate: candidate.published.toISOString().slice(0, 10),
  };
}

async function main() {
  console.log('Testing feed library...');

  const rnzFeed = FEEDS.find((feed) => feed.id === 'rnz');
  assert(rnzFeed, 'Expected RNZ feed definition to exist');
  const rnzResult = await fetchFeed(rnzFeed);
  assert(rnzResult.ok, `RNZ feed should succeed, got: ${rnzResult.error}`);
  assert(rnzResult.items.length > 0, 'RNZ feed should return items');
  assert(rnzResult.items[0].title.length > 0, 'RNZ items should have titles');
  assert(rnzResult.items[0].url.startsWith('http'), 'RNZ items should have URLs');
  console.log(`  ✓ RNZ feed: ${rnzResult.items.length} items`);

  const primaryResults = await fetchFeeds();
  const okCount = primaryResults.filter((result) => result.ok).length;
  assert(okCount >= 3, `At least 3 primary feeds should work, got ${okCount}`);
  console.log(`  ✓ Primary feeds: ${okCount}/${primaryResults.length} ok`);

  const allItems = primaryResults.flatMap((result) => result.items);
  const deduped = deduplicateItems(allItems);
  assert(deduped.length <= allItems.length, 'Deduplicated count should be <= total');
  assert(deduped.length > 0, 'Should have items after dedup');
  console.log(`  ✓ Dedup: ${allItems.length} → ${deduped.length} items`);

  const sorted = sortByDate(deduped);
  assert(sorted[0].published >= sorted[sorted.length - 1].published, 'Should be sorted newest first');
  console.log('  ✓ Sort: newest first');

  const filtered = filterByKeyword(allItems, 'new zealand');
  console.log(`  ✓ Keyword filter "new zealand": ${filtered.length} matches`);

  const searchCase = getSearchCase(sorted);
  console.log(`  ✓ Search case picked: "${searchCase.phrase}" from ${searchCase.item.sourceId}`);

  console.log('\nTesting CLI commands...');

  const headlinesJson = runCliJson(['headlines', '--limit', '5']);
  assert(typeof headlinesJson.sourcesOk === 'number', 'headlines JSON must include sourcesOk');
  assert(Array.isArray(headlinesJson.items), 'headlines JSON must include items array');
  assert((headlinesJson.items as unknown[]).length <= 5, 'headlines should respect --limit');
  console.log(`  ✓ headlines --limit 5: ${(headlinesJson.items as unknown[]).length} items`);

  const sourceJson = runCliJson(['source', 'rnz', '--limit', '3']);
  assert(sourceJson.sourceId === 'rnz', 'source should return rnz');
  assert(Array.isArray(sourceJson.items), 'source JSON must include items array');
  console.log(`  ✓ source rnz --limit 3: ${(sourceJson.items as unknown[]).length} items`);

  const sourcesJson = runCliJson(['sources']);
  assert(typeof sourcesJson.working === 'number', 'sources JSON must include working count');
  assert(Array.isArray(sourcesJson.sources), 'sources JSON must include sources array');
  console.log(`  ✓ sources: ${sourcesJson.working}/${sourcesJson.totalSources} working`);

  const summaryJson = runCliJson(['summary']);
  assert(typeof summaryJson.totalStories === 'number', 'summary JSON must include totalStories');
  assert(Array.isArray(summaryJson.top5), 'summary JSON must include top5 array');
  console.log(`  ✓ summary: ${summaryJson.totalStories} stories, ${(summaryJson.top5 as unknown[]).length} top headlines`);

  const topicJson = runCliJson(['topic', searchCase.singleWord, '--source', searchCase.item.sourceId]);
  assert(typeof topicJson.totalMatching === 'number', 'topic JSON must include totalMatching');
  assert((topicJson.totalMatching as number) >= 1, 'topic alias should find at least one match');
  console.log(`  ✓ topic alias: ${topicJson.totalMatching} matches for ${searchCase.singleWord}`);

  const searchJson = runCliJson([
    'search',
    '--keyword',
    searchCase.phrase,
    '--contains-all',
    '--source',
    searchCase.item.sourceId,
    '--since-date',
    searchCase.sinceDate,
  ]);
  assert(typeof searchJson.totalMatching === 'number', 'search JSON must include totalMatching');
  assert((searchJson.totalMatching as number) >= 1, 'search should find at least one match');
  assert((searchJson.matchMode as string) === 'contains-all', 'search should report contains-all mode');
  console.log(`  ✓ search filters: ${searchJson.totalMatching} matches for "${searchCase.phrase}"`);

  const exactJson = runCliJson([
    'search',
    '--keyword',
    searchCase.phrase,
    '--exact',
    '--source',
    searchCase.item.sourceId,
  ]);
  assert((exactJson.matchMode as string) === 'exact', 'exact search should report exact mode');
  console.log(`  ✓ exact search: ${exactJson.totalMatching} matches for "${searchCase.phrase}"`);

  console.log('\nNZ News smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
