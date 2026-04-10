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
  type FeedDefinition,
  type FeedResult,
  type NewsItem,
} from './feeds.js';

type CommonFlags = { json?: boolean; limit?: number };
type SearchFlags = CommonFlags & {
  keyword?: string;
  sinceHours?: number;
  sinceDate?: string;
  containsAll?: boolean;
  exact?: boolean;
  exclude?: string[];
  source?: string[];
};

type SearchFilters = {
  keyword: string;
  limit: number;
  sinceHours?: number;
  sinceDate?: string;
  containsAll?: boolean;
  exact?: boolean;
  exclude: string[];
  sourceIds: string[];
};

const nzDateTimeFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

function addExamples(command: Command, examples: string[]): Command {
  return command.addHelpText(
    'after',
    `\nExamples:\n${examples.map((example) => `  ${example}`).join('\n')}`,
  );
}

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

function parsePositiveNumber(raw: string): number {
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Expected a positive number, received: ${raw}`);
  }
  return value;
}

function parseSinceDate(raw: string): string {
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error(`Expected an ISO date or date-time, received: ${raw}`);
  }
  return parsed.toISOString();
}

function parseCsvList(raw: string): string[] {
  const values = raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

  if (values.length === 0) {
    throw new Error('Expected a comma-separated list with at least one value.');
  }

  return values;
}

function printOutput(data: unknown, json: boolean | undefined, render: () => string) {
  if (json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }
  console.log(render());
}

function collectItems(results: FeedResult[]): NewsItem[] {
  const all = results.flatMap((result) => result.items);
  return sortByDate(deduplicateItems(all));
}

function renderItems(items: NewsItem[], limit: number): string {
  const lines: string[] = [];
  const shown = items.slice(0, limit);
  shown.forEach((item, index) => {
    lines.push(`${index + 1}. ${item.title}`);
    lines.push(`   ${item.source} · ${formatDate(item.published)}`);
    lines.push(`   ${item.url}`);
  });
  return lines.join('\n');
}

function feedErrors(results: FeedResult[]): string {
  const failed = results.filter((result) => !result.ok);
  if (failed.length === 0) return '';
  return '\nFailed feeds: ' + failed.map((result) => `${result.feed.name} (${result.error})`).join(', ');
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

function normaliseSearchText(text: string): string {
  return text
    .replace(/<[^>]+>/g, ' ')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function searchableText(item: NewsItem): string {
  return normaliseSearchText(`${item.title} ${item.summary ?? ''}`);
}

function matchesKeyword(item: NewsItem, filters: SearchFilters): boolean {
  const haystack = searchableText(item);
  const keyword = normaliseSearchText(filters.keyword);

  if (!keyword) return true;

  if (filters.exact) {
    const exactPattern = new RegExp(`(^| )${escapeRegExp(keyword).replace(/ /g, ' +')}( |$)`, 'i');
    return exactPattern.test(haystack);
  }

  if (filters.containsAll) {
    const terms = keyword.split(' ').filter(Boolean);
    return terms.every((term) => haystack.includes(term));
  }

  return haystack.includes(keyword);
}

function withinSinceWindow(item: NewsItem, filters: SearchFilters): boolean {
  if (item.published.getTime() === 0) return false;

  if (typeof filters.sinceHours === 'number') {
    const cutoff = Date.now() - filters.sinceHours * 60 * 60 * 1000;
    return item.published.getTime() >= cutoff;
  }

  if (filters.sinceDate) {
    return item.published.getTime() >= Date.parse(filters.sinceDate);
  }

  return true;
}

function passesExcludeFilter(item: NewsItem, filters: SearchFilters): boolean {
  if (filters.exclude.length === 0) return true;
  const haystack = searchableText(item);
  return !filters.exclude.some((term) => haystack.includes(normaliseSearchText(term)));
}

function applySearchFilters(items: NewsItem[], filters: SearchFilters): NewsItem[] {
  return items.filter(
    (item) => withinSinceWindow(item, filters) && passesExcludeFilter(item, filters) && matchesKeyword(item, filters),
  );
}

function resolveFeed(name: string): FeedDefinition | undefined {
  const lower = name.toLowerCase();
  const exact = FEEDS.find((feed) => feed.id === lower || feed.name.toLowerCase() === lower);
  if (exact) return exact;

  const partialMatches = FEEDS.filter(
    (feed) => feed.id.startsWith(lower) || feed.name.toLowerCase().includes(lower),
  );

  return partialMatches.length === 1 ? partialMatches[0] : undefined;
}

function resolveSources(rawSources?: string[]): FeedDefinition[] {
  if (!rawSources || rawSources.length === 0) {
    return FEEDS.filter((feed) => PRIMARY_FEED_IDS.includes(feed.id));
  }

  const resolved = rawSources.map((rawSource) => {
    const feed = resolveFeed(rawSource);
    if (!feed) {
      throw new Error(`Unknown source: "${rawSource}". Run "nz-news sources" to see available sources.`);
    }
    return feed;
  });

  return resolved.filter((feed, index) => resolved.findIndex((candidate) => candidate.id === feed.id) === index);
}

function getKeyword(keywordParts: string[], keywordFlag?: string): string {
  const positional = keywordParts.join(' ').trim();
  const flag = keywordFlag?.trim() ?? '';

  if (positional && flag) {
    throw new Error('Use either a positional search term or --keyword, not both.');
  }

  const keyword = positional || flag;
  if (!keyword) {
    throw new Error('A search keyword is required. Try "nz-news search cyclone" or "nz-news search --keyword cyclone".');
  }

  return keyword;
}

function getMatchMode(filters: SearchFilters): 'substring' | 'contains-all' | 'exact' {
  if (filters.exact) return 'exact';
  if (filters.containsAll) return 'contains-all';
  return 'substring';
}

function formatSearchFilters(filters: SearchFilters, feeds: FeedDefinition[]): string[] {
  const lines: string[] = [];
  if (feeds.length > 0 && feeds.length !== PRIMARY_FEED_IDS.length) {
    lines.push(`Sources: ${feeds.map((feed) => feed.id).join(', ')}`);
  }
  if (typeof filters.sinceHours === 'number') {
    lines.push(`Since: last ${filters.sinceHours} hour${filters.sinceHours === 1 ? '' : 's'}`);
  }
  if (filters.sinceDate) {
    lines.push(`Since date: ${filters.sinceDate}`);
  }
  if (filters.containsAll) {
    lines.push('Match mode: all search terms must appear');
  }
  if (filters.exact) {
    lines.push('Match mode: exact phrase');
  }
  if (filters.exclude.length > 0) {
    lines.push(`Exclude: ${filters.exclude.join(', ')}`);
  }
  return lines;
}

const program = new Command();

program
  .name('nz-news')
  .description('Aggregate RSS feeds from New Zealand news websites.')
  .showHelpAfterError('(add --help for usage)');

addExamples(program, [
  'npx tsx skills/nz-news/scripts/cli.ts headlines',
  'npx tsx skills/nz-news/scripts/cli.ts search cyclone',
  'npx tsx skills/nz-news/scripts/cli.ts search --keyword cyclone --since-hours 24',
  'npx tsx skills/nz-news/scripts/cli.ts search --keyword "housing market" --contains-all --source rnz,newsroom',
  'npx tsx skills/nz-news/scripts/cli.ts topic cyclone --exclude sport --limit 5',
  'npx tsx skills/nz-news/scripts/cli.ts sources',
]);

addExamples(
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
        sourcesOk: results.filter((result) => result.ok).length,
        totalItems: items.length,
        returnedCount: shown.length,
        items: itemsToJson(shown),
        errors: results.filter((result) => !result.ok).map((result) => ({ source: result.feed.name, error: result.error })),
      };

      printOutput(output, options.json, () => {
        const lines = [`NZ Headlines — ${shown.length} of ${items.length} stories from ${output.sourcesOk} sources`];
        lines.push('');
        lines.push(renderItems(items, limit));
        lines.push(feedErrors(results));
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/nz-news/scripts/cli.ts headlines',
    'npx tsx skills/nz-news/scripts/cli.ts headlines --limit 20',
    'npx tsx skills/nz-news/scripts/cli.ts headlines --json',
  ],
);

addExamples(
  program
    .command('source <name>')
    .description('News from a specific source. Use "sources" to list available names and IDs.')
    .option('--limit <n>', 'number of items to show', parsePositiveInt, 10)
    .option('--json', 'emit machine-readable JSON')
    .action(async (name: string, options: CommonFlags) => {
      const feed = resolveFeed(name);
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
    }),
  [
    'npx tsx skills/nz-news/scripts/cli.ts source rnz',
    'npx tsx skills/nz-news/scripts/cli.ts source stuff --limit 5',
    'npx tsx skills/nz-news/scripts/cli.ts source herald --json',
  ],
);

addExamples(
  program
    .command('search [keyword...]')
    .alias('topic')
    .description('Search headlines and summaries across NZ sources. Accepts either a positional keyword or --keyword.')
    .option('--keyword <text>', 'search phrase, when you prefer flags over a positional argument')
    .option('--source <ids>', 'comma-separated source IDs or names, for example rnz,herald', parseCsvList)
    .option('--since-hours <hours>', 'only include stories from the last N hours', parsePositiveNumber)
    .option('--since-date <date>', 'only include stories on or after this ISO date or date-time', parseSinceDate)
    .option('--contains-all', 'for multi-word searches, require every search term to appear')
    .option('--exact', 'match the exact phrase instead of a loose substring search')
    .option('--exclude <terms>', 'comma-separated terms to exclude from title or summary matches', parseCsvList)
    .option('--limit <n>', 'number of items to show', parsePositiveInt, 10)
    .option('--json', 'emit machine-readable JSON')
    .action(async (keywordParts: string[], options: SearchFlags) => {
      if (options.containsAll && options.exact) {
        throw new Error('Use either --contains-all or --exact, not both.');
      }
      if (typeof options.sinceHours === 'number' && options.sinceDate) {
        throw new Error('Use either --since-hours or --since-date, not both.');
      }

      const keyword = getKeyword(keywordParts, options.keyword);
      const feeds = resolveSources(options.source);
      const limit = options.limit ?? 10;
      const filters: SearchFilters = {
        keyword,
        limit,
        sinceHours: options.sinceHours,
        sinceDate: options.sinceDate,
        containsAll: Boolean(options.containsAll),
        exact: Boolean(options.exact),
        exclude: options.exclude ?? [],
        sourceIds: feeds.map((feed) => feed.id),
      };

      const results = await fetchFeeds(filters.sourceIds);
      const all = collectItems(results);
      const filtered = applySearchFilters(all, filters);
      const shown = filtered.slice(0, limit);

      const output = {
        fetchedAt: new Date().toISOString(),
        keyword,
        matchMode: getMatchMode(filters),
        sourcesQueried: results.length,
        sourcesOk: results.filter((result) => result.ok).length,
        filters: {
          sourceIds: filters.sourceIds,
          sinceHours: filters.sinceHours ?? null,
          sinceDate: filters.sinceDate ?? null,
          exclude: filters.exclude,
          limit,
        },
        totalMatching: filtered.length,
        returnedCount: shown.length,
        items: itemsToJson(shown),
        errors: results.filter((result) => !result.ok).map((result) => ({ source: result.feed.name, error: result.error })),
      };

      printOutput(output, options.json, () => {
        const lines = [`NZ News search: "${keyword}" — ${filtered.length} matching stories`];
        const filterLines = formatSearchFilters(filters, feeds);
        if (filterLines.length > 0) {
          lines.push(...filterLines);
        }
        lines.push('');
        if (shown.length === 0) {
          lines.push('No stories matched those filters.');
        } else {
          lines.push(renderItems(filtered, limit));
        }
        lines.push(feedErrors(results));
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/nz-news/scripts/cli.ts search cyclone',
    'npx tsx skills/nz-news/scripts/cli.ts search --keyword cyclone --since-hours 24',
    'npx tsx skills/nz-news/scripts/cli.ts search --keyword "housing market" --contains-all --source rnz,newsroom',
    'npx tsx skills/nz-news/scripts/cli.ts search --keyword coalition --exact --since-date 2026-04-01',
    'npx tsx skills/nz-news/scripts/cli.ts topic cyclone --exclude sport --limit 5 --json',
  ],
);

addExamples(
  program
    .command('sources')
    .description('List all available news sources with a live status check.')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: { json?: boolean }) => {
      const results = await Promise.all(FEEDS.map(fetchFeed));

      const sourceList = results.map((result) => ({
        id: result.feed.id,
        name: result.feed.name,
        url: result.feed.url,
        format: result.feed.format,
        category: result.feed.category ?? null,
        primary: PRIMARY_FEED_IDS.includes(result.feed.id),
        status: result.ok ? 'ok' : 'error',
        itemCount: result.items.length,
        error: result.error ?? null,
        durationMs: result.durationMs,
      }));

      const output = {
        fetchedAt: new Date().toISOString(),
        totalSources: sourceList.length,
        working: sourceList.filter((source) => source.status === 'ok').length,
        failed: sourceList.filter((source) => source.status === 'error').length,
        sources: sourceList,
      };

      printOutput(output, options.json, () => {
        const lines = [`NZ News Sources — ${output.working}/${output.totalSources} working`];
        lines.push('');
        for (const source of sourceList) {
          const status = source.status === 'ok' ? `✓ ${source.itemCount} items` : `✗ ${source.error}`;
          const primary = source.primary ? '' : ' (category feed)';
          lines.push(`  ${source.id.padEnd(18)} ${source.name.padEnd(20)} ${status}${primary}`);
        }
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/nz-news/scripts/cli.ts sources',
    'npx tsx skills/nz-news/scripts/cli.ts sources --json',
  ],
);

addExamples(
  program
    .command('summary')
    .description('Brief summary: story count, source count, and top 5 headlines.')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: { json?: boolean }) => {
      const results = await fetchFeeds();
      const items = collectItems(results);
      const top5 = items.slice(0, 5);
      const okSources = results.filter((result) => result.ok);

      const output = {
        fetchedAt: new Date().toISOString(),
        sourcesQueried: results.length,
        sourcesOk: okSources.length,
        totalStories: items.length,
        top5: itemsToJson(top5),
        errors: results.filter((result) => !result.ok).map((result) => ({ source: result.feed.name, error: result.error })),
      };

      printOutput(output, options.json, () => {
        const lines = [
          `NZ News Summary — ${items.length} stories from ${okSources.length} sources`,
          '',
          'Top 5 headlines:',
        ];
        top5.forEach((item, index) => {
          lines.push(`  ${index + 1}. ${item.title} (${item.source})`);
        });
        lines.push(feedErrors(results));
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/nz-news/scripts/cli.ts summary',
    'npx tsx skills/nz-news/scripts/cli.ts summary --json',
  ],
);

async function main() {
  await program.parseAsync(process.argv);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
