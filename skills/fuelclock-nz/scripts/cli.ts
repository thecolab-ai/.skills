#!/usr/bin/env node
import { Command, Option } from 'commander';
import { pathToFileURL } from 'node:url';
import {
  getFuelPrices,
  getSupplyStatus,
  getVessels,
  type FuelPriceRow,
  type FuelState,
  type Vessel,
} from './client.js';

type JsonFlag = { json?: boolean };
type PriceFuelOption = '91' | '95' | '98' | 'diesel';
type SupplyFuelOption = 'petrol' | 'diesel' | 'jet';

type PriceView = {
  fuel: PriceFuelOption;
  label: string;
  price: number;
  change7d: number;
  change28d: number;
  changePercent28d: number;
  direction7d: string;
  direction28d: string;
  min: number;
  max: number;
  stationCount: number;
};

type SupplyView = {
  fuel: SupplyFuelOption;
  label: string;
  currentDays: number;
  totalDays: number;
  onLandDays: number;
  onWaterDays: number;
  msoThreshold: number;
  gapToMSODays: number;
  belowMSO: boolean;
  calendarDaysToDepletion: number;
  dailyConsumptionML: number;
  currentStockML: number;
  remainingOnWaterDays: number;
  remainingOnWaterML: number;
  mbieInCountryDays: number;
};

type VesselView = {
  name: string;
  fuel: SupplyFuelOption;
  status: string;
  eta: string | null;
  arrived: boolean;
  cargoML: number;
  cargoDays: number;
  origin: string;
  progressPct: number | null;
  flagRisk: boolean;
  flagReason?: string;
  hormuzTransit: boolean;
};

const program = new Command();
const priceFuelOrder: PriceFuelOption[] = ['91', '95', '98', 'diesel'];
const supplyFuelOrder: SupplyFuelOption[] = ['petrol', 'diesel', 'jet'];
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

function formatPrice(value: number): string {
  return `$${value.toFixed(3)}/L`;
}

function formatCents(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)} c/L`;
}

function formatDays(value: number): string {
  return `${value.toFixed(1)}d`;
}

function formatDirection(direction: string): string {
  return { up: '↑', down: '↓', flat: '→' }[direction] ?? direction;
}

function formatGapToMSO(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}d`;
}

function parsePositiveInt(raw: string): number {
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`Expected a positive integer, received: ${raw}`);
  }

  return value;
}

function priceRowFuel(row: FuelPriceRow): PriceFuelOption {
  const lower = row.type.toLowerCase();
  if (lower.includes('diesel')) return 'diesel';
  if (lower.startsWith('98')) return '98';
  if (lower.startsWith('95')) return '95';
  return '91';
}

function priceLabel(fuel: PriceFuelOption): string {
  return fuel === 'diesel' ? 'Diesel' : `${fuel} Unleaded`;
}

function selectPriceRows(rows: FuelPriceRow[], fuel?: PriceFuelOption): PriceView[] {
  return rows
    .filter((row) => !fuel || priceRowFuel(row) === fuel)
    .sort((left, right) => priceFuelOrder.indexOf(priceRowFuel(left)) - priceFuelOrder.indexOf(priceRowFuel(right)))
    .map((row) => ({
      fuel: priceRowFuel(row),
      label: row.type,
      price: row.price,
      change7d: row.change7d,
      change28d: row.change28d,
      changePercent28d: row.changePercent28d,
      direction7d: row.direction7d,
      direction28d: row.direction28d,
      min: row.min,
      max: row.max,
      stationCount: row.stationCount,
    }));
}

function toSupplyView(fuel: FuelState): SupplyView {
  return {
    fuel: fuel.fuelType as SupplyFuelOption,
    label: fuel.label,
    currentDays: fuel.currentDays,
    totalDays: fuel.totalDays,
    onLandDays: fuel.onLandDays,
    onWaterDays: fuel.onWaterDays,
    msoThreshold: fuel.msoThreshold,
    gapToMSODays: fuel.currentDays - fuel.msoThreshold,
    belowMSO: fuel.belowMSO,
    calendarDaysToDepletion: fuel.calendarDaysToDepletion,
    dailyConsumptionML: fuel.dailyConsumptionML / 1_000_000,
    currentStockML: fuel.currentStockML / 1_000_000,
    remainingOnWaterDays: fuel.remainingOnWaterDays,
    remainingOnWaterML: fuel.remainingOnWaterML / 1_000_000,
    mbieInCountryDays: fuel.mbieInCountryDays,
  };
}

function selectFuelStates(fuels: FuelState[], fuel?: SupplyFuelOption, belowMSO?: boolean): SupplyView[] {
  return fuels
    .filter((entry) => !fuel || entry.fuelType === fuel)
    .filter((entry) => !belowMSO || entry.belowMSO)
    .sort((left, right) => left.currentDays - right.currentDays)
    .map(toSupplyView);
}

function toVesselView(vessel: Vessel): VesselView {
  return {
    name: vessel.name,
    fuel: vessel.fuelType as SupplyFuelOption,
    status: vessel.status,
    eta: vessel.eta,
    arrived: vessel.arrived,
    cargoML: vessel.cargoML / 1_000_000,
    cargoDays: vessel.cargoDays,
    origin: vessel.origin,
    progressPct: vessel.progressPct ?? null,
    flagRisk: vessel.flagRisk,
    flagReason: vessel.flagReason,
    hormuzTransit: Boolean(vessel.hormuzTransit),
  };
}

function etaSortValue(vessel: Vessel): number {
  if (!vessel.eta) return Number.MAX_SAFE_INTEGER;
  const parsed = Date.parse(vessel.eta);
  return Number.isNaN(parsed) ? Number.MAX_SAFE_INTEGER : parsed;
}

function selectVesselRows(
  vessels: Vessel[],
  options: { fuel?: SupplyFuelOption; flaggedOnly?: boolean; limit?: number },
): VesselView[] {
  const filtered = vessels
    .filter((vessel) => !options.fuel || vessel.fuelType === options.fuel)
    .filter((vessel) => !options.flaggedOnly || vessel.flagRisk)
    .sort((left, right) => etaSortValue(left) - etaSortValue(right));

  const limited = typeof options.limit === 'number' ? filtered.slice(0, options.limit) : filtered;
  return limited.map(toVesselView);
}

function renderPrices(rows: PriceView[], fetchedAt: string, source: string, isFallback: boolean): string {
  const lines = [`NZ pump prices, ${source}, updated ${formatDateTime(fetchedAt)}`];

  for (const row of rows) {
    lines.push(
      `- ${row.label}: ${formatPrice(row.price)}, 7d ${formatDirection(row.direction7d)} ${formatCents(row.change7d)}, 28d ${formatDirection(row.direction28d)} ${formatCents(row.change28d)} (${row.changePercent28d.toFixed(1)}%), range ${formatPrice(row.min)} to ${formatPrice(row.max)} across ${row.stationCount.toLocaleString()} stations`,
    );
  }

  if (isFallback) {
    lines.push('');
    lines.push('Note: FuelClock reports this price snapshot came from fallback or cache data.');
  }

  return lines.join('\n');
}

function renderSupply(
  rows: SupplyView[],
  meta: { timestamp: string; overallRisk: string; countdownHours: number; lowestFuel?: SupplyView },
): string {
  const lines = [`NZ fuel supply, updated ${formatDateTime(meta.timestamp)}`];
  lines.push(`Overall risk: ${meta.overallRisk.toUpperCase()}`);

  if (meta.lowestFuel) {
    lines.push(
      `Tightest fuel: ${meta.lowestFuel.label}, ${formatDays(meta.lowestFuel.currentDays)} remaining, gap to MSO ${formatGapToMSO(meta.lowestFuel.gapToMSODays)}, depletion in ${formatDays(meta.lowestFuel.calendarDaysToDepletion)}`,
    );
  }

  lines.push(`Countdown: ${meta.countdownHours.toFixed(1)} hours (${formatDays(meta.countdownHours / 24)})`);
  lines.push('');

  if (rows.length === 0) {
    lines.push('No fuels matched the selected filters.');
    return lines.join('\n');
  }

  for (const row of rows) {
    const msoNote = row.belowMSO ? 'below MSO' : 'meets MSO';
    lines.push(
      `- ${row.label}: ${formatDays(row.currentDays)} current, MSO ${formatDays(row.msoThreshold)} (${formatGapToMSO(row.gapToMSODays)}, ${msoNote}), on-land ${formatDays(row.onLandDays)}, on-water ${formatDays(row.onWaterDays)}, depletion ${formatDays(row.calendarDaysToDepletion)}`,
    );
    lines.push(
      `  Stock ${row.currentStockML.toFixed(1)} ML, demand ${row.dailyConsumptionML.toFixed(1)} ML/day, remaining on-water ${row.remainingOnWaterML.toFixed(1)} ML (${formatDays(row.remainingOnWaterDays)}), MBIE in-country ${formatDays(row.mbieInCountryDays)}`,
    );
  }

  return lines.join('\n');
}

function renderVessels(
  rows: VesselView[],
  meta: { fetchedAt: string; source: string; totalMatching: number; govOnWaterByFuel?: Record<string, number> },
): string {
  const lines = [`Inbound fuel vessels, ${meta.source}, updated ${formatDateTime(meta.fetchedAt)}`];
  lines.push(`Showing ${rows.length} of ${meta.totalMatching} matching vessels.`);

  if (meta.govOnWaterByFuel) {
    const summary = supplyFuelOrder
      .filter((fuel) => typeof meta.govOnWaterByFuel?.[fuel] === 'number')
      .map((fuel) => `${fuel} ${meta.govOnWaterByFuel?.[fuel]?.toFixed(1)}`)
      .join(', ');
    if (summary) lines.push(`Gov on-water snapshot: ${summary}`);
  }

  lines.push('');

  if (rows.length === 0) {
    lines.push('No vessels matched the selected filters.');
    return lines.join('\n');
  }

  rows.forEach((row, index) => {
    lines.push(
      `${index + 1}. ${row.name}, ${row.fuel}, ${row.status}, ETA ${formatDateTime(row.eta)}, cargo ${row.cargoML.toFixed(1)} ML (${formatDays(row.cargoDays)}), origin ${row.origin}${typeof row.progressPct === 'number' ? `, progress ${row.progressPct.toFixed(1)}%` : ''}`,
    );
    if (row.flagRisk) lines.push(`   Flagged: ${row.flagReason ?? 'risk flagged by source'}`);
    if (row.hormuzTransit) lines.push('   Hormuz transit flagged.');
  });

  return lines.join('\n');
}

program
  .name('fuelclock-nz')
  .description('Query live New Zealand fuel prices, supply status, and inbound vessels from fuelclock.nz.')
  .showHelpAfterError('(add --help for usage)');

addExamples(program, [
  'npx tsx skills/fuelclock-nz/scripts/cli.ts summary',
  'npx tsx skills/fuelclock-nz/scripts/cli.ts prices --fuel diesel --json',
  'npx tsx skills/fuelclock-nz/scripts/cli.ts supply --below-mso',
  'npx tsx skills/fuelclock-nz/scripts/cli.ts vessels --flagged-only --limit 3',
]);

addExamples(
  program
    .command('summary')
    .description('Show a compact NZ fuel briefing across pump prices, supply, and inbound vessels.')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag) => {
      const [pricesData, supplyData, vesselsData] = await Promise.all([getFuelPrices(), getSupplyStatus(), getVessels()]);

      const prices = selectPriceRows(pricesData.prices);
      const fuels = selectFuelStates(supplyData.fuelStates);
      const vessels = selectVesselRows(vesselsData.vessels, { limit: 3 });
      const lowestFuel = supplyData.lowestFuel ? toSupplyView(supplyData.lowestFuel) : undefined;
      const belowMSO = fuels.filter((fuel) => fuel.belowMSO).map((fuel) => fuel.label);

      const summary = {
        prices: {
          fetchedAt: pricesData.fetchedAt,
          source: pricesData.source,
          isFallback: pricesData.isFallback,
          prices,
        },
        supply: {
          timestamp: supplyData.timestamp,
          overallRisk: supplyData.overallRisk,
          countdownHours: supplyData.countdownHours,
          lowestFuel,
          belowMSO,
          fuels,
        },
        vessels: {
          fetchedAt: vesselsData.fetchedAt,
          source: vesselsData.source,
          totalVessels: vesselsData.vessels.length,
          flaggedCount: vesselsData.vessels.filter((vessel) => vessel.flagRisk).length,
          vessels,
        },
      };

      printOutput(summary, options.json, () => {
        const lines = ['NZ fuel summary'];
        lines.push(`Updated: ${formatDateTime(pricesData.fetchedAt)}`);
        lines.push('');
        lines.push('Prices:');
        for (const row of prices) {
          lines.push(`- ${priceLabel(row.fuel)} ${formatPrice(row.price)} (${formatDirection(row.direction28d)} ${formatCents(row.change28d)} over 28d)`);
        }
        lines.push('');
        lines.push(`Supply: ${supplyData.overallRisk.toUpperCase()} risk, tightest fuel ${lowestFuel?.label ?? 'unknown'} at ${lowestFuel ? formatDays(lowestFuel.currentDays) : 'unknown'}, MSO flags: ${belowMSO.length > 0 ? belowMSO.join(', ') : 'none'}`);
        lines.push(
          `Vessels: ${vesselsData.vessels.length} inbound, ${summary.vessels.flaggedCount} flagged, next ETA ${vessels[0]?.eta ? formatDateTime(vessels[0].eta) : 'unknown'}`,
        );
        return lines.join('\n');
      });
    }),
  [
    'npx tsx skills/fuelclock-nz/scripts/cli.ts summary',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts summary --json',
  ],
);

addExamples(
  program
    .command('prices')
    .description('Show national average NZ pump prices, with optional fuel filtering.')
    .addOption(new Option('--fuel <fuel>', 'restrict to one fuel').choices(priceFuelOrder))
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { fuel?: PriceFuelOption }) => {
      const data = await getFuelPrices();
      const prices = selectPriceRows(data.prices, options.fuel);
      const output = {
        fetchedAt: data.fetchedAt,
        source: data.source,
        isFallback: data.isFallback,
        filters: { fuel: options.fuel ?? null },
        count: prices.length,
        prices,
      };

      printOutput(output, options.json, () => renderPrices(prices, data.fetchedAt, data.source, data.isFallback));
    }),
  [
    'npx tsx skills/fuelclock-nz/scripts/cli.ts prices',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts prices --fuel diesel',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts prices --fuel 95 --json',
  ],
);

addExamples(
  program
    .command('supply')
    .description('Show NZ fuel supply days remaining, with optional fuel filtering and below-MSO selection.')
    .addOption(new Option('--fuel <fuel>', 'restrict to one fuel').choices(supplyFuelOrder))
    .option('--below-mso', 'only show fuels currently below their minimum stock obligation threshold')
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { fuel?: SupplyFuelOption; belowMso?: boolean }) => {
      const data = await getSupplyStatus();
      const fuels = selectFuelStates(data.fuelStates, options.fuel, options.belowMso);
      const lowestFuel = data.lowestFuel ? toSupplyView(data.lowestFuel) : undefined;
      const output = {
        timestamp: data.timestamp,
        anchorDate: data.anchorDate,
        mbieAsAtDate: data.mbieAsAtDate,
        overallRisk: data.overallRisk,
        countdownHours: data.countdownHours,
        lowestFuel,
        filters: {
          fuel: options.fuel ?? null,
          belowMSO: Boolean(options.belowMso),
        },
        count: fuels.length,
        fuels,
      };

      printOutput(output, options.json, () =>
        renderSupply(fuels, {
          timestamp: data.timestamp,
          overallRisk: data.overallRisk,
          countdownHours: data.countdownHours,
          lowestFuel,
        }),
      );
    }),
  [
    'npx tsx skills/fuelclock-nz/scripts/cli.ts supply',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts supply --below-mso',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts supply --fuel diesel --json',
  ],
);

addExamples(
  program
    .command('vessels')
    .description('Show inbound fuel vessels, with optional fuel, flagged-only, and limit filters.')
    .addOption(new Option('--fuel <fuel>', 'restrict to one fuel').choices(supplyFuelOrder))
    .option('--flagged-only', 'only show vessels flagged by the source as higher-risk or uncertain')
    .option('--limit <n>', 'limit the number of vessels returned', parsePositiveInt)
    .option('--json', 'emit machine-readable JSON')
    .action(async (options: JsonFlag & { fuel?: SupplyFuelOption; flaggedOnly?: boolean; limit?: number }) => {
      const data = await getVessels();
      const matchingVessels = data.vessels
        .filter((vessel) => !options.fuel || vessel.fuelType === options.fuel)
        .filter((vessel) => !options.flaggedOnly || vessel.flagRisk);
      const vessels = selectVesselRows(data.vessels, options);
      const output = {
        fetchedAt: data.fetchedAt,
        source: data.source,
        govOnWaterByFuel: data.govOnWaterByFuel ?? null,
        filters: {
          fuel: options.fuel ?? null,
          flaggedOnly: Boolean(options.flaggedOnly),
          limit: options.limit ?? null,
        },
        totalMatching: matchingVessels.length,
        returnedCount: vessels.length,
        vessels,
      };

      printOutput(output, options.json, () =>
        renderVessels(vessels, {
          fetchedAt: data.fetchedAt,
          source: data.source,
          totalMatching: matchingVessels.length,
          govOnWaterByFuel: data.govOnWaterByFuel,
        }),
      );
    }),
  [
    'npx tsx skills/fuelclock-nz/scripts/cli.ts vessels',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts vessels --flagged-only --limit 3',
    'npx tsx skills/fuelclock-nz/scripts/cli.ts vessels --fuel diesel --json',
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
