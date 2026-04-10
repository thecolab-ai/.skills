#!/usr/bin/env node
import { Command } from 'commander';
import { pathToFileURL } from 'node:url';
import {
  FEEDS,
  PRIMARY_FEED_IDS,
  fetchFeed,
  fetchFeeds,
  deduplicateItems,
  sortByDate,
  filterByKeyword,
  type FeedResult,
  type NewsItem,
} from './feeds.js';

type CommonFlags = { json?: boolean; limit?: number };

const nzDateTimeFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

function formatDate(date: Date): string {
  if (date.getTime() === 0) return 'unknown';
  return nzDateTimeFormatter.format(date);
}

function parsePositiveInt(raw: string): number {
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`Expected a positive integer, received: ${raw}`);
  }
  return value;
}

function printOutput(data: unknown, json: boolean | undefined, render: () => string) {
  if (json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }
  console.log(render());
}

function collectItems(results: FeedResult[]): NewsItem[] {
  const all = results.flatMap((r) => r.items);
  return sortByDate(deduplicateItems(all));
}

function renderItems(items: NewsItem[], limit: number): string {
  const lines: string[] = [];
  const shown = items.slice(0, limit);
  shown.forEach((item, i) => {
    lines.push(`${i + 1}. ${item.title}`);
    lines.push(`   ${item.source} · ${formatDate(item.published)}`);
    lines.push(`   ${item.url}`);
  });
  return lines.join('\n');
}

function feedErrors(results: FeedResult[]): string {
  const failed = results.filter((r) => !r.ok);
  if (failed.length === 0) return '';
  return '\nFailed feeds: ' + failed.map((r) => `${r.feed.name} (${r.error})`).join(', ');
}

function itemsToJson(items: NewsItem[]) {
  return items.map((item) => ({
    title: item.title,
    url: item.url,
    published: item.published.toISOString(),
    source: item.source,
    sourceId: item.sourceId,
    summary: item.summary ?? null,
  }));
}

const program = new Command();

program
  .name('nz-news')
  .description('Aggregate RSS feeds from New Zealand news websites.')
  .showHelpAfterError('(add --help for usage)');

program
  .command('headlines')
  .description('Top headlines across all primary sources, deduplicated and sorted by date.')
  .option('--limit <n>', 'number of items to show', parsePositiveInt, 10)
  .option('--json', 'emit machine-readable JSON')
  .action(async (options: CommonFlags) => {
    const limit = options.limit ?? 10;
    const results = await fetchFeeds();
    const items = collectItems(results);
    const shown = items.slice(0, limit);

    const output = {
      fetchedAt: new Date().toISOString(),
      sourcesQueried: results.length,
      sourcesOk: results.filter((r) => r.ok).length,
      totalItems: items.length,
      returnedCount: shown.length,
      items: itemsToJson(shown),
      errors: results.filter((r) => !r.ok).map((r) => ({ source: r.feed.name, error: r.error })),
    };

    printOutput(output, options.json, () => {
      const lines = [`NZ Headlines — ${shown.length} of ${items.length} stories from ${output.sourcesOk} sources`];
      lines.push('');
      lines.push(renderItems(items, limit));
      lines.push(feedErrors(results));
      return lines.join('\n');
    });
  });

program
  .command('source <name>')
  .description('News from a specific source. Use "sources" command to list available names.')
  .option('--limit <n>', 'number of items to show', parsePositiveInt, 10)
  .option('--json', 'emit machine-readable JSON')
  .action(async (name: string, options: CommonFlags) => {
    const lower = name.toLowerCase();
    const feed = FEEDS.find(
      (f) => f.id === lower || f.name.toLowerCase() === lower || f.id.startsWith(lower),
    );
    if (!feed) {
      console.error(`Unknown source: "${name}". Run "nz-news sources" to see available sources.`);
      process.exit(1);
    }
    const limit = options.limit ?? 10;
    const result = await fetchFeed(feed);
    if (!result.ok) {
      console.error(`Failed to fetch ${feed.name}: ${result.error}`);
      process.exit(1);
    }
    const items = sortByDate(result.items).slice(0, limit);

    const output = {
      fetchedAt: new Date().toISOString(),
      source: feed.name,
      sourceId: feed.id,
      totalItems: result.items.length,
      returnedCount: items.length,
      items: itemsToJson(items),
    };

    printOutput(output, options.json, () => {
      const lines = [`${feed.name} — ${items.length} of ${result.items.length} stories`];
      lines.push('');
      lines.push(renderItems(items, limit));
      return lines.join('\n');
    });
  });

program
  .command('topic <keyword>')
  .description('Filter headlines by keyword across all primary sources.')
  .option('--limit <n>', 'number of items to show', parsePositiveInt, 10)
  .option('--json', 'emit machine-readable JSON')
  .action(async (keyword: string, options: CommonFlags) => {
    const limit = options.limit ?? 10;
    const results = await fetchFeeds();
    const all = collectItems(results);
    const filtered = filterByKeyword(all, keyword);
    const shown = filtered.slice(0, limit);

    const output = {
      fetchedAt: new Date().toISOString(),
      keyword,
      sourcesQueried: results.length,
      sourcesOk: results.filter((r) => r.ok).length,
      totalMatching: filtered.length,
      returnedCount: shown.length,
      items: itemsToJson(shown),
      errors: results.filter((r) => !r.ok).map((r) => ({ source: r.feed.name, error: r.error })),
    };

    printOutput(output, options.json, () => {
      const lines = [`NZ News: "${keyword}" — ${filtered.length} matching stories`];
      lines.push('');
      if (shown.length === 0) {
        lines.push('No stories matched that keyword.');
      } else {
        lines.push(renderItems(filtered, limit));
      }
      lines.push(feedErrors(results));
      return lines.join('\n');
    });
  });

program
  .command('sources')
  .description('List all available news sources with live status check.')
  .option('--json', 'emit machine-readable JSON')
  .action(async (options: { json?: boolean }) => {
    const results = await Promise.all(FEEDS.map(fetchFeed));

    const sourceList = results.map((r) => ({
      id: r.feed.id,
      name: r.feed.name,
      url: r.feed.url,
      format: r.feed.format,
      category: r.feed.category ?? null,
      primary: PRIMARY_FEED_IDS.includes(r.feed.id),
      status: r.ok ? 'ok' : 'error',
      itemCount: r.items.length,
      error: r.error ?? null,
      durationMs: r.durationMs,
    }));

    const output = {
      fetchedAt: new Date().toISOString(),
      totalSources: sourceList.length,
      working: sourceList.filter((s) => s.status === 'ok').length,
      failed: sourceList.filter((s) => s.status === 'error').length,
      sources: sourceList,
    };

    printOutput(output, options.json, () => {
      const lines = [`NZ News Sources — ${output.working}/${output.totalSources} working`];
      lines.push('');
      for (const s of sourceList) {
        const status = s.status === 'ok' ? `✓ ${s.itemCount} items` : `✗ ${s.error}`;
        const primary = s.primary ? '' : ' (category feed)';
        lines.push(`  ${s.id.padEnd(18)} ${s.name.padEnd(20)} ${status}${primary}`);
      }
      return lines.join('\n');
    });
  });

program
  .command('summary')
  .description('Brief summary: story count, source count, and top 5 headlines.')
  .option('--json', 'emit machine-readable JSON')
  .action(async (options: { json?: boolean }) => {
    const results = await fetchFeeds();
    const items = collectItems(results);
    const top5 = items.slice(0, 5);
    const okSources = results.filter((r) => r.ok);

    const output = {
      fetchedAt: new Date().toISOString(),
      sourcesQueried: results.length,
      sourcesOk: okSources.length,
      totalStories: items.length,
      top5: itemsToJson(top5),
      errors: results.filter((r) => !r.ok).map((r) => ({ source: r.feed.name, error: r.error })),
    };

    printOutput(output, options.json, () => {
      const lines = [
        `NZ News Summary — ${items.length} stories from ${okSources.length} sources`,
        '',
        'Top 5 headlines:',
      ];
      top5.forEach((item, i) => {
        lines.push(`  ${i + 1}. ${item.title} (${item.source})`);
      });
      lines.push(feedErrors(results));
      return lines.join('\n');
    });
  });

async function main() {
  await program.parseAsync(process.argv);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
