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

async function main() {
  const [prices, supply] = await Promise.all([getFuelPrices(), getSupplyStatus()]);
  console.log(`FuelClock NZ client is reachable. Prices: ${prices.prices.length}, fuels: ${supply.fuelStates.length}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
