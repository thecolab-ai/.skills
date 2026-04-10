import { pathToFileURL } from 'node:url';

const BASE_URL = 'https://fuelclock.nz';
const DEFAULT_TIMEOUT_MS = 10_000;

export type FuelRiskLevel = 'normal' | 'elevated' | 'critical';

export interface FuelPriceRow {
  type: string;
  price: number;
  change7d: number;
  change28d: number;
  direction7d: 'up' | 'down' | 'flat' | string;
  direction28d: 'up' | 'down' | 'flat' | string;
  changePercent28d: number;
  min: number;
  max: number;
  stationCount: number;
}

export interface FuelPricesResponse {
  prices: FuelPriceRow[];
  source: string;
  fetchedAt: string;
  gaspyTimestamp?: number;
  isFallback: boolean;
}

export interface FuelState {
  fuelType: string;
  label: string;
  currentDays: number;
  totalDays: number;
  onLandDays: number;
  msoThreshold: number;
  belowMSO: boolean;
  dailyConsumptionML: number;
  currentStockML: number;
  totalStockML: number;
  onLandStockML: number;
  anchorStockML: number;
  mbieInCountryDays: number;
  mbieInCountryML: number;
  onWaterML: number;
  onWaterDays: number;
  confirmedOnWaterML: number;
  confirmedOnWaterDays: number;
  aisConfirmedOnWaterDays: number;
  aisConfirmedOnWaterML: number;
  pipelineArrivedDays: number;
  remainingOnWaterDays: number;
  remainingOnWaterML: number;
  hoursElapsed: number;
  weightedDaysElapsed: number;
  arrivedVesselDays: number;
  calendarDaysToDepletion: number;
}

export interface SupplyStatusResponse {
  timestamp: string;
  anchorDate: string;
  mbieAsAtDate: string;
  fuelStates: FuelState[];
  overallRisk: FuelRiskLevel;
  countdownHours: number;
  lowestFuel?: FuelState;
  vessels?: unknown[];
  mbieClaimed?: boolean;
}

export interface MbieStocksResponse {
  asAtDate: string;
  asAtDateParsed: string;
  inCountryDays: Record<string, number>;
  onWaterDays: Record<string, number>;
  totalDays: Record<string, number>;
  combined: Record<string, number>;
  shipments: unknown[];
  dailyDemand: Record<string, number>;
  nextUpdate: string;
  fetchedAt: string;
  isFallback: boolean;
}

export interface Vessel {
  name: string;
  fuelType: string;
  cargoML: number;
  cargoDays: number;
  origin: string;
  status: string;
  eta: string | null;
  arrived: boolean;
  flagRisk: boolean;
  flagReason?: string;
  hormuzTransit?: boolean;
  originLat?: number;
  originLng?: number;
  destLat?: number;
  destLng?: number;
  progressPct?: number;
}

export interface VesselsResponse {
  vessels: Vessel[];
  source: string;
  govOnWaterByFuel?: Record<string, number>;
  fetchedAt: string;
}

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

export async function getFuelPrices(): Promise<FuelPricesResponse> {
  return getJson<FuelPricesResponse>('/api/fuel-prices');
}

export async function getSupplyStatus(): Promise<SupplyStatusResponse> {
  return getJson<SupplyStatusResponse>('/api/fuel-data');
}

export async function getMbieStocks(): Promise<MbieStocksResponse> {
  return getJson<MbieStocksResponse>('/api/mbie-stocks');
}

export async function getVessels(): Promise<VesselsResponse> {
  return getJson<VesselsResponse>('/api/vessels');
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

function formatDeltaCents(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)} c/L`;
}

function formatFuelStatus(fuel: FuelState): string {
  const status = fuel.belowMSO ? 'below MSO' : 'meets MSO';
  return `${status}, depletion in ${fuel.calendarDaysToDepletion.toFixed(1)} days`;
}

export async function getSummary(): Promise<string> {
  const [pricesData, supplyData] = await Promise.all([getFuelPrices(), getSupplyStatus()]);

  const lines: string[] = [];
  lines.push(`NZ Fuel Summary (${pricesData.fetchedAt ?? supplyData.timestamp ?? 'unknown'})`);
  lines.push('');
  lines.push('Retail pump prices (NZD/litre, national average):');

  for (const price of pricesData.prices) {
    const arrow = { up: '↑', down: '↓', flat: '→' }[price.direction7d] ?? '';
    lines.push(
      `  ${price.type}: $${price.price.toFixed(3)}/L ${arrow} (7d: ${formatDeltaCents(price.change7d)}, 28d: ${formatDeltaCents(price.change28d)})`,
    );
  }

  lines.push('');
  lines.push(`Supply security: overall risk = ${supplyData.overallRisk.toUpperCase()}`);
  if (typeof supplyData.countdownHours === 'number') {
    lines.push(
      `  Most constrained fuel depletes in ${supplyData.countdownHours.toFixed(1)} hours (${(supplyData.countdownHours / 24).toFixed(1)} days)`,
    );
  }

  lines.push('');
  lines.push('Days of supply remaining:');
  for (const fuel of supplyData.fuelStates) {
    lines.push(
      `  ${fuel.label}: ${fuel.currentDays.toFixed(1)} days (MSO threshold: ${fuel.msoThreshold} days)${fuel.belowMSO ? ' [BELOW MSO]' : ''}`,
    );
    lines.push(`    Status: ${formatFuelStatus(fuel)}`);
  }

  if (pricesData.isFallback) {
    lines.push('');
    lines.push('Note: price data is currently being served from cache.');
  }

  return lines.join('\n');
}

async function main() {
  console.log(await getSummary());
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
