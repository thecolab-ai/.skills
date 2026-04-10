#!/usr/bin/env node
import { Command } from 'commander';
import { pathToFileURL } from 'node:url';
import {
  LOCATIONS,
  resolveLocation,
  fetchCurrentConditions,
  fetchHourlyForecast,
  fetchDailyForecast,
  fetchMarineForecast,
  fetchWindForecast,
  fetchRainForecast,
  fetchCycloneData,
  fetchPressureTrend,
  scrapeWarnings,
  type Location,
} from './client.js';

type JsonFlag = { json?: boolean; location?: string };

const program = new Command();

const nzTimeFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

const nzDateTimeFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
});

const nzDateFormatter = new Intl.DateTimeFormat('en-NZ', {
  timeZone: 'Pacific/Auckland',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
});

function formatTime(iso: string): string {
  return nzTimeFormatter.format(new Date(iso));
}

function formatDateTime(iso: string): string {
  return nzDateTimeFormatter.format(new Date(iso));
}

function formatDate(iso: string): string {
  return nzDateFormatter.format(new Date(iso));
}

function degToCompass(deg: number | null): string {
  if (deg === null) return '?';
  const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return dirs[Math.round(deg / 22.5) % 16];
}

function num(v: number | null, decimals: number = 1): string {
  return v !== null ? v.toFixed(decimals) : '-';
}

function printOutput(data: unknown, json: boolean | undefined, render: () => string) {
  if (json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }
  console.log(render());
}

function getLocation(args: { location?: string }, positional?: string): Location {
  return resolveLocation(positional, args.location);
}

function padRight(s: string, len: number): string {
  return s.length >= len ? s : s + ' '.repeat(len - s.length);
}

program
  .name('metservice-nz')
  .description('Query NZ weather data from the MetOcean API.')
  .showHelpAfterError('(add --help for usage)');

// --- now ---
program
  .command('now')
  .description('Current conditions snapshot')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const c = await fetchCurrentConditions(loc);

    printOutput(c, options.json, () => {
      const lines: string[] = [];
      lines.push(`📍 ${loc.name} — Current Conditions`);
      lines.push(`   ${formatDateTime(c.time)} NZST`);
      lines.push(`🌡️  Temp: ${num(c.tempC)}°C`);
      lines.push(`💧 Humidity: ${num(c.humidity, 0)}%`);
      lines.push(`💨 Wind: ${num(c.windSpeedKmh, 0)} km/h ${degToCompass(c.windDirDeg)}  Gusts: ${num(c.gustSpeedKmh, 0)} km/h`);
      lines.push(`🌧️  Rain: ${num(c.rainMmH)} mm/h`);
      lines.push(`☁️  Cloud: ${num(c.cloudCoverPct, 0)}%`);
      lines.push(`🔵 Pressure: ${num(c.pressureHpa, 0)} hPa`);
      if (c.visibilityKm !== null) {
        lines.push(`👁️  Visibility: ${num(c.visibilityKm)} km`);
      }
      if (c.solarWm2 !== null) {
        lines.push(`☀️  Solar: ${num(c.solarWm2, 0)} W/m²`);
      }
      return lines.join('\n');
    });
  });

// --- forecast ---
program
  .command('forecast')
  .description('24-hour hourly forecast')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchHourlyForecast(loc);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`📍 ${loc.name} — 24h Forecast`);
      lines.push('');
      lines.push(`${'Time'.padEnd(10)} ${'Temp'.padEnd(7)} ${'Rain'.padEnd(9)} ${'Wind'.padEnd(12)} ${'Gust'.padEnd(9)} ${'Cloud'.padEnd(6)} Dir`);
      lines.push('─'.repeat(62));

      for (const h of data.hours) {
        const time = padRight(formatTime(h.time), 10);
        const temp = padRight(`${num(h.tempC)}°`, 7);
        const rain = padRight(`${num(h.rainMmH)}mm/h`, 9);
        const wind = padRight(`${num(h.windSpeedKmh, 0)}km/h`, 12);
        const gust = padRight(`${num(h.gustSpeedKmh, 0)}km/h`, 9);
        const cloud = padRight(`${num(h.cloudCoverPct, 0)}%`, 6);
        const dir = degToCompass(h.windDirDeg);
        lines.push(`${time} ${temp} ${rain} ${wind} ${gust} ${cloud} ${dir}`);
      }

      return lines.join('\n');
    });
  });

// --- daily ---
program
  .command('daily')
  .description('7-day daily summary')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchDailyForecast(loc);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`📍 ${loc.name} — 7-Day Forecast`);
      lines.push('');
      lines.push(`${'Day'.padEnd(14)} ${'High'.padEnd(7)} ${'Low'.padEnd(7)} ${'Rain'.padEnd(8)} ${'Wind'.padEnd(10)} ${'Gust'.padEnd(9)} ${'Cloud'.padEnd(6)} Dir`);
      lines.push('─'.repeat(72));

      for (const d of data.days) {
        // Parse the NZ date string back for formatting
        const day = padRight(d.date, 14);
        const high = padRight(`${num(d.highC)}°`, 7);
        const low = padRight(`${num(d.lowC)}°`, 7);
        const rain = padRight(`${num(d.totalRainMm)}mm`, 8);
        const wind = padRight(`${num(d.avgWindKmh, 0)}km/h`, 10);
        const gust = padRight(d.maxGustKmh !== null ? `${num(d.maxGustKmh, 0)}km/h` : '-', 9);
        const cloud = padRight(`${num(d.avgCloudPct, 0)}%`, 6);
        const dir = degToCompass(d.dominantWindDir);
        lines.push(`${day} ${high} ${low} ${rain} ${wind} ${gust} ${cloud} ${dir}`);
      }

      return lines.join('\n');
    });
  });

// --- marine ---
program
  .command('marine')
  .description('Marine forecast: waves, swell, sea temperature')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchMarineForecast(loc);

    // Check if we got any wave data
    const hasData = data.hours.some(h => h.waveHeightM !== null);
    if (!hasData) {
      console.log(`📍 ${loc.name} — No marine data available (location may be too far inland).`);
      console.log('Try a coastal location or use --location with offshore coordinates.');
      return;
    }

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`🌊 ${loc.name} — Marine Forecast`);
      lines.push('');
      lines.push(`${'Time'.padEnd(10)} ${'Wave'.padEnd(7)} ${'Swell'.padEnd(7)} ${'Period'.padEnd(8)} ${'Dir'.padEnd(5)} ${'WindSea'.padEnd(8)} ${'SeaTemp'.padEnd(7)}`);
      lines.push('─'.repeat(58));

      for (const h of data.hours) {
        const time = padRight(formatTime(h.time), 10);
        const wave = padRight(h.waveHeightM !== null ? `${num(h.waveHeightM)}m` : '-', 7);
        const swell = padRight(h.swellHeightM !== null ? `${num(h.swellHeightM)}m` : '-', 7);
        const period = padRight(h.swellPeriodS !== null ? `${num(h.swellPeriodS)}s` : (h.wavePeriodS !== null ? `${num(h.wavePeriodS)}s` : '-'), 8);
        const dir = padRight(degToCompass(h.swellDirectionDeg ?? h.waveDirectionDeg), 5);
        const windSea = padRight(h.windSeaHeightM !== null ? `${num(h.windSeaHeightM)}m` : '-', 8);
        const seaTemp = h.seaTempC !== null ? `${num(h.seaTempC)}°` : '-';
        lines.push(`${time} ${wave} ${swell} ${period} ${dir} ${windSea} ${seaTemp}`);
      }

      return lines.join('\n');
    });
  });

// --- wind ---
program
  .command('wind')
  .description('Detailed wind forecast: speed, gusts, direction')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchWindForecast(loc);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`💨 ${loc.name} — Wind Forecast`);
      lines.push('');
      lines.push(`${'Time'.padEnd(10)} ${'Speed'.padEnd(10)} ${'Gust'.padEnd(10)} ${'Dir'.padEnd(5)} Compass`);
      lines.push('─'.repeat(45));

      for (const h of data.hours) {
        const time = padRight(formatTime(h.time), 10);
        const speed = padRight(`${num(h.speedKmh, 0)} km/h`, 10);
        const gust = padRight(`${num(h.gustKmh, 0)} km/h`, 10);
        const dirDeg = padRight(h.directionDeg !== null ? `${h.directionDeg.toFixed(0)}°` : '-', 5);
        const compass = degToCompass(h.directionDeg);
        lines.push(`${time} ${speed} ${gust} ${dirDeg} ${compass}`);
      }

      return lines.join('\n');
    });
  });

// --- rain ---
program
  .command('rain')
  .description('Precipitation forecast')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchRainForecast(loc);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`🌧️  ${loc.name} — Rain Forecast`);
      lines.push('');
      lines.push(`${'Time'.padEnd(10)} ${'Rain'.padEnd(10)} ${'Cloud'.padEnd(6)} Bar`);
      lines.push('─'.repeat(45));

      for (const h of data.hours) {
        const time = padRight(formatTime(h.time), 10);
        const rain = padRight(`${num(h.rainMmH)} mm/h`, 10);
        const cloud = padRight(`${num(h.cloudCoverPct, 0)}%`, 6);
        const barLen = Math.round((h.rainMmH ?? 0) * 10);
        const bar = barLen > 0 ? '█'.repeat(Math.min(barLen, 30)) : '';
        lines.push(`${time} ${rain} ${cloud} ${bar}`);
      }

      const total = data.hours.reduce((sum, h) => sum + (h.rainMmH ?? 0), 0);
      lines.push('');
      lines.push(`Total rainfall estimate: ${num(total)} mm over ${data.hours.length}h`);

      return lines.join('\n');
    });
  });

// --- warnings ---
program
  .command('warnings')
  .description('Scrape MetService severe weather warnings')
  .option('--json', 'emit machine-readable JSON')
  .action(async (options: JsonFlag) => {
    const data = await scrapeWarnings();

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push('⚠️  MetService Warnings');
      lines.push(`   Fetched: ${formatDateTime(data.fetchedAt)} NZST`);
      lines.push(`   Source: ${data.source}`);
      lines.push('');

      if (data.warnings.length === 0) {
        lines.push('   No active warnings found.');
      } else {
        for (const w of data.warnings) {
          const level = w.level ? `[${w.level.toUpperCase()}]` : '';
          lines.push(`   ${level} ${w.type}: ${w.description}`);
          if (w.areas) lines.push(`      Areas: ${w.areas}`);
          if (w.timing) lines.push(`      Timing: ${w.timing}`);
        }
      }

      if (data.outlook) {
        lines.push('');
        lines.push(`   Outlook: ${data.outlook}`);
      }

      if (data.raw) {
        lines.push('');
        lines.push('   Raw relevant content:');
        const wrapped = data.raw.substring(0, 500);
        lines.push(`   ${wrapped}`);
      }

      lines.push('');
      lines.push('   Also check:');
      lines.push('   • https://www.metservice.com/warnings/severe-weather-outlook');
      lines.push('   • https://www.metservice.com/marine-surf/tropical-cyclones');

      return lines.join('\n');
    });
  });

// --- cyclone ---
program
  .command('cyclone')
  .description('Cyclone-specific data: pressure, extreme wind, storm surge indicators')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .option('--hours <n>', 'hours to forecast', '48')
  .action(async (positional: string | undefined, options: JsonFlag & { hours?: string }) => {
    const loc = getLocation(options, positional);
    const hours = parseInt(options.hours ?? '48', 10);
    const data = await fetchCycloneData(loc, hours);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`🌀 ${loc.name} — Cyclone Tracker`);
      lines.push(`   ${formatDateTime(data.time)} NZST`);
      lines.push('');

      // Current snapshot
      lines.push('  CURRENT CONDITIONS:');
      const pLabel = data.pressureHpa !== null && data.pressureHpa < 990 ? '⛔' :
                     data.pressureHpa !== null && data.pressureHpa < 1000 ? '⚠️ ' : '  ';
      lines.push(`  ${pLabel} Pressure: ${num(data.pressureHpa, 1)} hPa${data.pressureHpa !== null && data.pressureHpa < 990 ? ' — CYCLONE TERRITORY' : ''}`);

      const wLabel = data.gustSpeedKmh !== null && data.gustSpeedKmh > 118 ? '⛔' :
                     data.gustSpeedKmh !== null && data.gustSpeedKmh > 63 ? '⚠️ ' : '  ';
      lines.push(`  ${wLabel} Wind: ${num(data.windSpeedKmh, 0)} km/h sustained, ${num(data.gustSpeedKmh, 0)} km/h gusts ${degToCompass(data.windDirDeg)}`);
      if (data.gustSpeedKmh !== null && data.gustSpeedKmh > 118) lines.push('       ^^^ SEVERE TROPICAL CYCLONE WIND SPEEDS');
      else if (data.gustSpeedKmh !== null && data.gustSpeedKmh > 63) lines.push('       ^^^ TROPICAL CYCLONE WIND SPEEDS');

      lines.push(`     Wave: ${num(data.waveHeightM)} m  Swell: ${num(data.swellHeightM)} m  Period: ${num(data.wavePeriodS, 0)} s`);
      lines.push(`     Rain: ${num(data.rainMmH)} mm/h`);
      lines.push('');

      // Pressure trend from first 6 hours
      const pressReadings = data.hours.slice(0, 6).filter(h => h.pressureHpa !== null);
      if (pressReadings.length >= 2) {
        const first = pressReadings[0].pressureHpa!;
        const last = pressReadings[pressReadings.length - 1].pressureHpa!;
        const change = last - first;
        const ratePerHour = change / (pressReadings.length - 1);
        lines.push(`  PRESSURE TREND (next ${pressReadings.length - 1}h): ${change >= 0 ? '+' : ''}${change.toFixed(1)} hPa (${ratePerHour >= 0 ? '+' : ''}${ratePerHour.toFixed(1)} hPa/hr)`);
        if (ratePerHour <= -3) lines.push('  ⛔ DANGER: Rapid pressure drop — severe cyclone intensification');
        else if (ratePerHour <= -1) lines.push('  ⚠️  Pressure falling — storm approaching');
        lines.push('');
      }

      // Find peak conditions
      const maxGust = Math.max(...data.hours.map(h => h.gustSpeedKmh ?? 0));
      const minPressure = Math.min(...data.hours.filter(h => h.pressureHpa !== null).map(h => h.pressureHpa!));
      const maxWave = Math.max(...data.hours.map(h => h.waveHeightM ?? 0));
      const maxRain = Math.max(...data.hours.map(h => h.rainMmH ?? 0));

      lines.push(`  PEAK CONDITIONS (next ${hours}h):`);
      lines.push(`     Min pressure: ${minPressure.toFixed(1)} hPa`);
      lines.push(`     Max gust: ${maxGust.toFixed(0)} km/h`);
      lines.push(`     Max wave: ${maxWave.toFixed(1)} m`);
      lines.push(`     Max rain rate: ${maxRain.toFixed(1)} mm/h`);
      lines.push('');

      // Hourly table
      lines.push(`  ${'Time'.padEnd(10)} ${'Press'.padEnd(9)} ${'Wind'.padEnd(10)} ${'Gust'.padEnd(10)} ${'Dir'.padEnd(5)} ${'Wave'.padEnd(7)} ${'Rain'.padEnd(8)}`);
      lines.push('  ' + '─'.repeat(64));

      for (const h of data.hours) {
        const time = padRight(formatTime(h.time), 10);
        const press = padRight(h.pressureHpa !== null ? `${h.pressureHpa.toFixed(1)}` : '-', 9);
        const wind = padRight(`${num(h.windSpeedKmh, 0)}km/h`, 10);
        const gust = padRight(`${num(h.gustSpeedKmh, 0)}km/h`, 10);
        const dir = padRight(degToCompass(h.windDirDeg), 5);
        const wave = padRight(h.waveHeightM !== null ? `${num(h.waveHeightM)}m` : '-', 7);
        const rain = `${num(h.rainMmH)}mm/h`;
        lines.push(`  ${time} ${press} ${wind} ${gust} ${dir} ${wave} ${rain}`);
      }

      lines.push('');
      lines.push('  Thresholds: Pressure <990 hPa = cyclone | Wind >63 km/h = TC | >118 km/h = severe TC');
      lines.push('  Pressure drop >3 hPa/hr = rapid intensification');

      return lines.join('\n');
    });
  });

// --- pressure ---
program
  .command('pressure')
  .description('Barometric pressure trend — key cyclone indicator')
  .argument('[location]', 'named location or lat,lon')
  .option('--json', 'emit machine-readable JSON')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .action(async (positional: string | undefined, options: JsonFlag) => {
    const loc = getLocation(options, positional);
    const data = await fetchPressureTrend(loc);

    printOutput(data, options.json, () => {
      const lines: string[] = [];
      lines.push(`🔵 ${loc.name} — Pressure Trend`);
      lines.push('');

      lines.push(`   Current: ${num(data.currentHpa, 1)} hPa`);
      lines.push(`   Trend: ${data.trend.direction.toUpperCase()}`);
      if (data.trend.changePerHour !== null)
        lines.push(`   Rate: ${data.trend.changePerHour >= 0 ? '+' : ''}${data.trend.changePerHour.toFixed(2)} hPa/hr`);
      if (data.trend.change3h !== null)
        lines.push(`   3h change: ${data.trend.change3h >= 0 ? '+' : ''}${data.trend.change3h.toFixed(1)} hPa`);
      if (data.trend.change6h !== null)
        lines.push(`   6h change: ${data.trend.change6h >= 0 ? '+' : ''}${data.trend.change6h.toFixed(1)} hPa`);
      if (data.trend.severity)
        lines.push(`   ${data.trend.severity}`);
      lines.push('');

      // Mini chart
      lines.push('   12h history → 12h forecast:');
      lines.push(`   ${'Time'.padEnd(10)} ${'hPa'.padEnd(10)} Bar`);
      lines.push('   ' + '─'.repeat(50));

      const validReadings = data.readings.filter(r => r.pressureHpa !== null);
      if (validReadings.length > 0) {
        const minP = Math.min(...validReadings.map(r => r.pressureHpa!));
        const maxP = Math.max(...validReadings.map(r => r.pressureHpa!));
        const range = Math.max(maxP - minP, 1);

        for (const r of data.readings) {
          const time = padRight(formatTime(r.time), 10);
          const hpa = r.pressureHpa !== null ? padRight(r.pressureHpa.toFixed(1), 10) : padRight('-', 10);
          const barLen = r.pressureHpa !== null ? Math.round(((r.pressureHpa - minP) / range) * 30) : 0;
          const bar = barLen > 0 ? '█'.repeat(barLen) : '';
          lines.push(`   ${time} ${hpa} ${bar}`);
        }
      }

      lines.push('');
      lines.push('   Key: >3 hPa/hr drop = DANGER (rapid cyclone intensification)');
      lines.push('        <990 hPa = tropical cyclone territory');

      return lines.join('\n');
    });
  });

// --- watch ---
program
  .command('watch')
  .description('Continuous cyclone monitoring — polls every 5 min, alerts on changes')
  .argument('[location]', 'named location or lat,lon')
  .option('--location <coords>', 'custom coordinates as lat,lon')
  .option('--interval <minutes>', 'polling interval in minutes', '5')
  .option('--json', 'emit machine-readable JSON per poll')
  .action(async (positional: string | undefined, options: JsonFlag & { interval?: string }) => {
    const loc = getLocation(options, positional);
    const intervalMs = parseInt(options.interval ?? '5', 10) * 60 * 1000;
    let lastPressure: number | null = null;
    let pollCount = 0;

    console.log(`🌀 Watching ${loc.name} — polling every ${options.interval ?? '5'} min (Ctrl+C to stop)`);
    console.log('');

    const poll = async () => {
      pollCount++;
      try {
        const data = await fetchCycloneData(loc, 6);
        const current = data.hours[0];
        if (!current) return;

        const now = formatDateTime(data.time);
        const pressureChange = lastPressure !== null && current.pressureHpa !== null
          ? current.pressureHpa - lastPressure
          : null;

        if (options.json) {
          console.log(JSON.stringify({
            poll: pollCount,
            time: data.time,
            pressureHpa: current.pressureHpa,
            pressureChange,
            windSpeedKmh: current.windSpeedKmh,
            gustSpeedKmh: current.gustSpeedKmh,
            windDir: degToCompass(current.windDirDeg),
            waveHeightM: current.waveHeightM,
            rainMmH: current.rainMmH,
          }));
        } else {
          const changeStr = pressureChange !== null ? ` (${pressureChange >= 0 ? '+' : ''}${pressureChange.toFixed(1)})` : '';
          const alert = current.pressureHpa !== null && current.pressureHpa < 990 ? ' ⛔ CYCLONE' :
                        current.gustSpeedKmh !== null && current.gustSpeedKmh > 118 ? ' ⛔ SEVERE WIND' :
                        current.gustSpeedKmh !== null && current.gustSpeedKmh > 63 ? ' ⚠️  HIGH WIND' :
                        pressureChange !== null && pressureChange < -3 ? ' ⛔ RAPID DROP' : '';

          console.log(
            `[${now}] P: ${num(current.pressureHpa, 1)} hPa${changeStr} | ` +
            `Wind: ${num(current.windSpeedKmh, 0)}/${num(current.gustSpeedKmh, 0)} km/h ${degToCompass(current.windDirDeg)} | ` +
            `Wave: ${num(current.waveHeightM)}m | Rain: ${num(current.rainMmH)}mm/h${alert}`
          );
        }

        lastPressure = current.pressureHpa;
      } catch (err) {
        console.error(`[Poll ${pollCount}] Error: ${err instanceof Error ? err.message : String(err)}`);
      }
    };

    await poll();
    setInterval(poll, intervalMs);
  });

// --- locations ---
program
  .command('locations')
  .description('List known locations')
  .option('--json', 'emit machine-readable JSON')
  .action((options: JsonFlag) => {
    const locs = Object.entries(LOCATIONS).map(([key, loc]) => ({
      key,
      name: loc.name,
      lat: loc.lat,
      lon: loc.lon,
    }));

    printOutput(locs, options.json, () => {
      const lines: string[] = [];
      lines.push('📍 Known Locations');
      lines.push('');
      lines.push(`${'Key'.padEnd(15)} ${'Name'.padEnd(18)} ${'Lat'.padEnd(10)} Lon`);
      lines.push('─'.repeat(55));
      for (const loc of locs) {
        lines.push(`${padRight(loc.key, 15)} ${padRight(loc.name, 18)} ${padRight(loc.lat.toFixed(4), 10)} ${loc.lon.toFixed(4)}`);
      }
      lines.push('');
      lines.push('Usage: <command> <location>  (e.g. now auckland)');
      lines.push('Custom: --location lat,lon  (e.g. --location -37.0,175.5)');
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
