import {
  getFuelPrices,
  getSupplyStatus,
  getMbieStocks,
  getVessels,
  getGeopoliticalRisk,
  getNews,
  getSummary,
} from './client.js';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

async function main() {
  const prices = await getFuelPrices();
  assert(Array.isArray(prices.prices), 'prices.prices must be an array');

  const supply = await getSupplyStatus();
  assert(Array.isArray(supply.fuelStates), 'supply.fuelStates must be an array');
  assert(typeof supply.overallRisk === 'string', 'supply.overallRisk must be a string');

  const mbie = await getMbieStocks();
  assert(typeof mbie.asAtDate === 'string', 'mbie.asAtDate must be a string');

  const vessels = await getVessels();
  assert(Array.isArray(vessels.vessels), 'vessels.vessels must be an array');

  const risk = await getGeopoliticalRisk();
  assert(Array.isArray(risk.markets), 'risk.markets must be an array');

  const news = await getNews();
  assert(Array.isArray(news.articles), 'news.articles must be an array');

  const summary = await getSummary();
  assert(summary.includes('NZ Fuel Summary'), 'summary must include the title');

  console.log('FuelClock NZ smoke test passed.');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
