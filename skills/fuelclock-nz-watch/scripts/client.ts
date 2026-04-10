import { pathToFileURL } from 'node:url';

const BASE_URL = 'https://fuelclock.nz';
const DEFAULT_TIMEOUT_MS = 10_000;

export interface GeopoliticalRiskMarket {
  id: string;
  slug: string;
  title: string;
  shortTitle?: string;
  probability: number;
  volume: number;
  liquidity?: number;
  description?: string;
  endDate?: string;
  outcomes?: string[];
  lastUpdated?: string;
  isFallback?: boolean;
  subMarkets?: Array<{ label: string; probability: number }>;
}

export interface GeopoliticalRiskResponse {
  markets: GeopoliticalRiskMarket[];
  fetchedAt: string | null;
}

export interface NewsArticle {
  title: string;
  url: string;
  source: string;
  date: string;
}

export interface NewsResponse {
  articles: NewsArticle[];
  fetchedAt: string;
}

async function getJson<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }

    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getGeopoliticalRisk(): Promise<GeopoliticalRiskResponse> {
  const markets = await getJson<GeopoliticalRiskMarket[]>('/api/polymarket');
  const fetchedAt = markets.reduce<string | null>((latest, market) => {
    if (!market.lastUpdated) return latest;
    if (!latest) return market.lastUpdated;
    return market.lastUpdated > latest ? market.lastUpdated : latest;
  }, null);

  return { markets, fetchedAt };
}

export async function getNews(): Promise<NewsResponse> {
  return getJson<NewsResponse>('/api/news');
}

async function main() {
  const [risk, news] = await Promise.all([getGeopoliticalRisk(), getNews()]);
  console.log(`FuelClock NZ watch client is reachable. Markets: ${risk.markets.length}, articles: ${news.articles.length}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
