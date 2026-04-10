#!/usr/bin/env node
import { Command } from 'commander';
import { pathToFileURL } from 'node:url';
import {
  getGeopoliticalRisk,
  getNews,
  type GeopoliticalRiskMarket,
  type NewsArticle,
} from './client.js';

type JsonFlag = { json?: boolean };

type RiskView = {
  title: string;
  shortTitle?: string;
  probability: number;
  volume: number;
  liquidity?: number;
  lastUpdated?: string;
  isFallback?: boolean;
  subMarkets: Array<{ label: string; probability: number }>;
};

type NewsView = {
  title: string;
  source: string;
  date: string;
  url: string;
};

const program = new Command();
const nzDateTimeFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZoneName: 'short',
});

function addExamples(command: Command, examples: string[]): Command {
  return command.addHelpText(
    'after',
    `\nExamples:\n${examples.map((example) => `  ${example}`).join('\n')}`,
  );
}

function printOutput(data: unknown, json: boolean | undefined, render: () => string) {
  if (json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(render());
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'unknown';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return nzDateTimeFormatter.format(date);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function parsePositiveInt(raw: string): number {
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`Expected a positive integer, received: ${raw}`);
  }

  return value;
}

function selectRiskRows(markets: GeopoliticalRiskMarket[], limit?: number): RiskView[] {
  const sorted = [...markets]
    .sort((left, right) => right.volume - left.volume || right.probability - left.probability)
    .slice(0, limit ?? markets.length);

  return sorted.map((market) => ({
    title: market.title,
    shortTitle: market.shortTitle,
    probability: market.probability,
    volume: market.volume,
    liquidity: market.liquidity,
    lastUpdated: market.lastUpdated,
    isFallback: market.isFallback,
    subMarkets: market.subMarkets ?? [],
  }));
}

function selectNewsRows(articles: NewsArticle[], limit?: number): NewsView[] {
  return [...articles]
    .sort((left, right) => Date.parse(right.date) - Date.parse(left.date))
    .slice(0, limit ?? articles.length)
    .map((article) => ({
      title: article.title,
      source: article.source,
      date: article.date,
      url: article.url,
    }));
}

function renderRisk(rows: RiskView[], fetchedAt: string | null): string {
  const lines = ['Tracked geopolitical fuel-shipping markets'];
  lines.push(`Latest market update: ${formatDateTime(fetchedAt)}`);
  lines.push('Sorted by trading volume. The probability shown is the market yes-price, not a direct NZ fuel risk score.');
  lines.push('');

  if (rows.length === 0) {
    lines.push('No markets returned.');
    return lines.join('\n');
  }

  for (const row of rows) {
    lines.push(
      `- ${row.shortTitle ?? row.title}: ${formatPercent(row.probability)} yes, $${row.volume.toLocaleString(undefined, { maximumFractionDigits: 0 })} volume${typeof row.liquidity === 'number' ? `, $${row.liquidity.toLocaleString(undefined, { maximumFractionDigits: 0 })} liquidity` : ''}, updated ${formatDateTime(row.lastUpdated)}`,
    );
    if (row.subMarkets.length > 0) {
      lines.push(
        `  Sub-markets: ${row.subMarkets.map((market) => `${market.label} ${formatPercent(market.probability)}`).join(', ')}`,
      );
    }
  }

  return lines.join('\n');
}

function renderNews(rows: NewsView[], fetchedAt: string): string {
  const lines = [`Recent NZ fuel headlines, updated ${formatDateTime(fetchedAt)}`];
  lines.push('');

  if (rows.length === 0) {
    lines.push('No articles returned.');
    return lines.join('\n');
  }

  rows.forEach((row, index) => {
    lines.push(`${index + 1}. ${row.title}`);
    lines.push(`   ${row.source}, ${formatDateTime(row.date)}`);
    lines.push(`   ${row.url}`);
  });

  return lines.join('\n');
}

program
  .name('fuelclock-nz-watch')
  .description('Monitor NZ fuel watch signals, including shipping-related markets and recent fuel headlines.')
  .showHelpAfterError('(add --help for usage)');

addExamples(program, [
  'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts summary',
  'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk --limit 5',
  'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news --limit 3 --json',
]);

addExamples(
  program
    .command('summary')
    .description('Show a compact fuel watch briefing across top markets and recent headlines.')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag) => {
      const [riskData, newsData] = await Promise.all([getGeopoliticalRisk(), getNews()]);
      const markets = selectRiskRows(riskData.markets, 3);
      const articles = selectNewsRows(newsData.articles, 3);

      const summary = {
        risk: {
          fetchedAt: riskData.fetchedAt,
          totalMarkets: riskData.markets.length,
          markets,
        },
        news: {
          fetchedAt: newsData.fetchedAt,
          totalArticles: newsData.articles.length,
          articles,
        },
      };

      printOutput(summary, options.json, () => {
        const lines = ['NZ fuel watch summary'];
        lines.push(`Market update: ${formatDateTime(riskData.fetchedAt)}`);
        lines.push(`Headline update: ${formatDateTime(newsData.fetchedAt)}`);
        lines.push('');
        if (markets[0]) {
          lines.push(
            `Top market: ${markets[0].shortTitle ?? markets[0].title} at ${formatPercent(markets[0].probability)} yes on $${markets[0].volume.toLocaleString(undefined, { maximumFractionDigits: 0 })} volume`,
          );
        }
        if (articles[0]) {
          lines.push(`Latest headline: ${articles[0].title} (${articles[0].source})`);
        }
        if (!markets[0] && !articles[0]) {
          lines.push('No watch items returned.');
        }
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts summary',
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts summary --json',
  ],
);

addExamples(
  program
    .command('risk')
    .description('Show tracked geopolitical markets relevant to fuel shipping, sorted by market volume.')
    .option('--limit <n>', 'limit the number of markets returned', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { limit?: number }) => {
      const data = await getGeopoliticalRisk();
      const markets = selectRiskRows(data.markets, options.limit);
      const output = {
        fetchedAt: data.fetchedAt,
        sort: 'volume-desc',
        filters: {
          limit: options.limit ?? null,
        },
        totalMarkets: data.markets.length,
        returnedCount: markets.length,
        markets,
      };

      printOutput(output, options.json, () => renderRisk(markets, data.fetchedAt));
    }),
  [
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk',
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk --limit 5',
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts risk --limit 3 --json',
  ],
);

addExamples(
  program
    .command('news')
    .description('Show recent NZ fuel headlines, newest first.')
    .option('--limit <n>', 'limit the number of articles returned', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { limit?: number }) => {
      const data = await getNews();
      const articles = selectNewsRows(data.articles, options.limit);
      const output = {
        fetchedAt: data.fetchedAt,
        filters: {
          limit: options.limit ?? null,
        },
        totalArticles: data.articles.length,
        returnedCount: articles.length,
        articles,
      };

      printOutput(output, options.json, () => renderNews(articles, data.fetchedAt));
    }),
  [
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news',
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news --limit 3',
    'npx tsx skills/fuelclock-nz-watch/scripts/cli.ts news --limit 5 --json',
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
