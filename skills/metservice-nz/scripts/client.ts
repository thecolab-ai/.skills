import { pathToFileURL } from 'node:url';

const API_BASE = 'https://forecast-v2.metoceanapi.com/point/time';
const API_KEY = process.env.METOCEAN_API_KEY;
if (!API_KEY) throw new Error('METOCEAN_API_KEY env var not set. Sign up at https://forecast-v2.metoceanapi.com and add it to your .env');
const DEFAULT_TIMEOUT_MS = 15_000;

export interface Location {
  name: string;
  lat: number;
  lon: number;
}

export const LOCATIONS: Record<string, Location> = {
  clevedon: { name: 'Clevedon', lat: -36.9697, lon: 175.0752 },
  auckland: { name: 'Auckland CBD', lat: -36.8485, lon: 174.7633 },
  wellington: { name: 'Wellington', lat: -41.2865, lon: 174.7762 },
  christchurch: { name: 'Christchurch', lat: -43.5321, lon: 172.6362 },
  queenstown: { name: 'Queenstown', lat: -45.0312, lon: 168.6626 },
};

export const LOCATION_NAMES = Object.keys(LOCATIONS);

export interface PointTimeRequest {
  points: Array<{ lon: number; lat: number }>;
  variables: string[];
  time: { from: string; interval: string; repeat: number };
}

export interface VariableData {
  standardName?: string;
  units: string;
  siUnits?: string;
  dimensions: string[];
  data: Array<number | null>;
  noData: number[];
}

export interface PointTimeResponse {
  dimensions: {
    point: { type: string; data: Array<{ lon: number; lat: number }> };
    time: { type: string; data: string[] };
  };
  variables: Record<string, VariableData>;
}

export async function queryPointTime(request: PointTimeRequest): Promise<PointTimeResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(API_BASE, {
      method: 'POST',
      headers: {
        'x-api-key': API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`MetOcean API error: ${response.status} ${response.statusText}${body ? ` — ${body}` : ''}`);
    }

    return (await response.json()) as PointTimeResponse;
  } finally {
    clearTimeout(timeout);
  }
}

// --- Variable groups ---

export const WEATHER_VARS = [
  'air.temperature.at-2m',
  'air.humidity.at-2m',
  'air.pressure.at-sea-level',
  'air.visibility',
  'cloud.cover',
  'precipitation.rate',
  'wind.speed.at-10m',
  'wind.direction.at-10m',
  'wind.speed.gust.at-10m',
  'radiation.flux.downward.shortwave',
];

export const WIND_VARS = [
  'wind.speed.at-10m',
  'wind.direction.at-10m',
  'wind.speed.gust.at-10m',
];

export const RAIN_VARS = [
  'precipitation.rate',
  'cloud.cover',
];

export const MARINE_VARS = [
  'wave.height',
  'wave.height.primary-swell',
  'wave.height.wind-sea',
  'wave.period.peak',
  'wave.period.primary-swell.peak',
  'wave.direction.peak',
  'wave.direction.primary-swell.mean',
  'sea.temperature.at-surface',
];

export const CYCLONE_VARS = [
  'air.pressure.at-sea-level',
  'wind.speed.at-10m',
  'wind.speed.gust.at-10m',
  'wind.direction.at-10m',
  'wave.height',
  'wave.height.primary-swell',
  'wave.period.peak',
  'precipitation.rate',
];

// --- Helpers ---

function nowISOHour(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function resolveLocation(nameOrCoords?: string, coordsFlag?: string): Location {
  if (coordsFlag) {
    const [lat, lon] = coordsFlag.split(',').map(Number);
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      throw new Error(`Invalid coordinates: ${coordsFlag}. Expected format: lat,lon`);
    }
    return { name: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon };
  }

  if (nameOrCoords) {
    const key = nameOrCoords.toLowerCase().trim();
    if (LOCATIONS[key]) return LOCATIONS[key];

    // Try parsing as lat,lon
    if (key.includes(',')) {
      const [lat, lon] = key.split(',').map(Number);
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
        return { name: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon };
      }
    }

    const available = Object.keys(LOCATIONS).join(', ');
    throw new Error(`Unknown location: ${nameOrCoords}. Available: ${available}`);
  }

  const available = Object.keys(LOCATIONS).join(', ');
  throw new Error(`Please specify a location: ${available} — or use --location lat,lon`);
}

export async function fetchCurrentConditions(location: Location): Promise<{
  location: Location;
  time: string;
  tempC: number | null;
  humidity: number | null;
  pressureHpa: number | null;
  visibilityKm: number | null;
  cloudCoverPct: number | null;
  rainMmH: number | null;
  windSpeedKmh: number | null;
  windDirDeg: number | null;
  gustSpeedKmh: number | null;
  solarWm2: number | null;
}> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: WEATHER_VARS,
    time: { from, interval: '1h', repeat: 1 },
  });

  const v = data.variables;
  const get = (key: string): number | null => v[key]?.data?.[0] ?? null;

  const tempK = get('air.temperature.at-2m');
  const pressurePa = get('air.pressure.at-sea-level');
  const visM = get('air.visibility');
  const windMs = get('wind.speed.at-10m');
  const gustMs = get('wind.speed.gust.at-10m');
  const cloudFrac = get('cloud.cover');
  const rain = get('precipitation.rate');

  return {
    location,
    time: data.dimensions.time.data[0] ?? from,
    tempC: tempK !== null ? tempK - 273.15 : null,
    humidity: get('air.humidity.at-2m'),
    pressureHpa: pressurePa !== null ? pressurePa / 100 : null,
    visibilityKm: visM !== null ? visM / 1000 : null,
    cloudCoverPct: cloudFrac,
    rainMmH: rain !== null ? Math.max(0, rain) : null,
    windSpeedKmh: windMs !== null ? windMs * 3.6 : null,
    windDirDeg: get('wind.direction.at-10m'),
    gustSpeedKmh: gustMs !== null ? gustMs * 3.6 : null,
    solarWm2: get('radiation.flux.downward.shortwave'),
  };
}

export async function fetchHourlyForecast(location: Location, hours: number = 24): Promise<{
  location: Location;
  hours: Array<{
    time: string;
    tempC: number | null;
    rainMmH: number | null;
    windSpeedKmh: number | null;
    windDirDeg: number | null;
    gustSpeedKmh: number | null;
    cloudCoverPct: number | null;
    humidity: number | null;
  }>;
}> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: [...WEATHER_VARS],
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const getArr = (key: string): Array<number | null> => v[key]?.data ?? [];

  const tempArr = getArr('air.temperature.at-2m');
  const rainArr = getArr('precipitation.rate');
  const windArr = getArr('wind.speed.at-10m');
  const dirArr = getArr('wind.direction.at-10m');
  const gustArr = getArr('wind.speed.gust.at-10m');
  const cloudArr = getArr('cloud.cover');
  const humArr = getArr('air.humidity.at-2m');

  const hoursList = times.map((time, i) => ({
    time,
    tempC: tempArr[i] !== null && tempArr[i] !== undefined ? tempArr[i]! - 273.15 : null,
    rainMmH: rainArr[i] !== null && rainArr[i] !== undefined ? Math.max(0, rainArr[i]!) : null,
    windSpeedKmh: windArr[i] !== null && windArr[i] !== undefined ? windArr[i]! * 3.6 : null,
    windDirDeg: dirArr[i] ?? null,
    gustSpeedKmh: gustArr[i] !== null && gustArr[i] !== undefined ? gustArr[i]! * 3.6 : null,
    cloudCoverPct: cloudArr[i] ?? null,
    humidity: humArr[i] ?? null,
  }));

  return { location, hours: hoursList };
}

export async function fetchDailyForecast(location: Location, days: number = 7): Promise<{
  location: Location;
  days: Array<{
    date: string;
    highC: number | null;
    lowC: number | null;
    totalRainMm: number;
    avgWindKmh: number | null;
    maxGustKmh: number | null;
    dominantWindDir: number | null;
    avgCloudPct: number | null;
  }>;
}> {
  const hours = days * 24;
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: ['air.temperature.at-2m', 'precipitation.rate', 'wind.speed.at-10m', 'wind.direction.at-10m', 'wind.speed.gust.at-10m', 'cloud.cover'],
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const tempArr = v['air.temperature.at-2m']?.data ?? [];
  const rainArr = v['precipitation.rate']?.data ?? [];
  const windArr = v['wind.speed.at-10m']?.data ?? [];
  const dirArr = v['wind.direction.at-10m']?.data ?? [];
  const gustArr = v['wind.speed.gust.at-10m']?.data ?? [];
  const cloudArr = v['cloud.cover']?.data ?? [];

  // Group by date (NZ timezone)
  const dayMap = new Map<string, number[]>();
  for (let i = 0; i < times.length; i++) {
    const nzDate = new Date(times[i]).toLocaleDateString('en-NZ', { timeZone: 'Pacific/Auckland', year: 'numeric', month: '2-digit', day: '2-digit' });
    if (!dayMap.has(nzDate)) dayMap.set(nzDate, []);
    dayMap.get(nzDate)!.push(i);
  }

  const daysList = Array.from(dayMap.entries()).map(([date, indices]) => {
    const temps = indices.map(i => tempArr[i]).filter((v): v is number => v !== null && v !== undefined);
    const rains = indices.map(i => rainArr[i]).filter((v): v is number => v !== null && v !== undefined);
    const winds = indices.map(i => windArr[i]).filter((v): v is number => v !== null && v !== undefined);
    const gusts = indices.map(i => gustArr[i]).filter((v): v is number => v !== null && v !== undefined);
    const dirs = indices.map(i => dirArr[i]).filter((v): v is number => v !== null && v !== undefined);
    const clouds = indices.map(i => cloudArr[i]).filter((v): v is number => v !== null && v !== undefined);

    return {
      date,
      highC: temps.length > 0 ? Math.max(...temps) - 273.15 : null,
      lowC: temps.length > 0 ? Math.min(...temps) - 273.15 : null,
      totalRainMm: rains.reduce((sum, r) => sum + Math.max(0, r), 0),
      avgWindKmh: winds.length > 0 ? (winds.reduce((a, b) => a + b, 0) / winds.length) * 3.6 : null,
      maxGustKmh: gusts.length > 0 ? Math.max(...gusts) * 3.6 : null,
      dominantWindDir: dirs.length > 0 ? dirs[Math.floor(dirs.length / 2)] : null,
      avgCloudPct: clouds.length > 0 ? clouds.reduce((a, b) => a + b, 0) / clouds.length : null,
    };
  });

  return { location, days: daysList };
}

export async function fetchMarineForecast(location: Location, hours: number = 24): Promise<{
  location: Location;
  hours: Array<{
    time: string;
    waveHeightM: number | null;
    swellHeightM: number | null;
    windSeaHeightM: number | null;
    wavePeriodS: number | null;
    swellPeriodS: number | null;
    waveDirectionDeg: number | null;
    swellDirectionDeg: number | null;
    seaTempC: number | null;
  }>;
}> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: MARINE_VARS,
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const getArr = (key: string): Array<number | null> => v[key]?.data ?? [];

  const waveH = getArr('wave.height');
  const swellH = getArr('wave.height.primary-swell');
  const windSeaH = getArr('wave.height.wind-sea');
  const waveP = getArr('wave.period.peak');
  const swellP = getArr('wave.period.primary-swell.peak');
  const waveD = getArr('wave.direction.peak');
  const swellD = getArr('wave.direction.primary-swell.mean');
  const seaT = getArr('sea.temperature.at-surface');

  const hoursList = times.map((time, i) => ({
    time,
    waveHeightM: waveH[i] ?? null,
    swellHeightM: swellH[i] ?? null,
    windSeaHeightM: windSeaH[i] ?? null,
    wavePeriodS: waveP[i] ?? null,
    swellPeriodS: swellP[i] ?? null,
    waveDirectionDeg: waveD[i] ?? null,
    swellDirectionDeg: swellD[i] ?? null,
    seaTempC: seaT[i] !== null && seaT[i] !== undefined ? seaT[i]! - 273.15 : null,
  }));

  return { location, hours: hoursList };
}

export async function fetchWindForecast(location: Location, hours: number = 24): Promise<{
  location: Location;
  hours: Array<{
    time: string;
    speedKmh: number | null;
    gustKmh: number | null;
    directionDeg: number | null;
  }>;
}> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: WIND_VARS,
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const windArr = v['wind.speed.at-10m']?.data ?? [];
  const gustArr = v['wind.speed.gust.at-10m']?.data ?? [];
  const dirArr = v['wind.direction.at-10m']?.data ?? [];

  const hoursList = times.map((time, i) => ({
    time,
    speedKmh: windArr[i] !== null && windArr[i] !== undefined ? windArr[i]! * 3.6 : null,
    gustKmh: gustArr[i] !== null && gustArr[i] !== undefined ? gustArr[i]! * 3.6 : null,
    directionDeg: dirArr[i] ?? null,
  }));

  return { location, hours: hoursList };
}

export async function fetchRainForecast(location: Location, hours: number = 24): Promise<{
  location: Location;
  hours: Array<{
    time: string;
    rainMmH: number | null;
    cloudCoverPct: number | null;
  }>;
}> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: RAIN_VARS,
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const rainArr = v['precipitation.rate']?.data ?? [];
  const cloudArr = v['cloud.cover']?.data ?? [];

  const hoursList = times.map((time, i) => ({
    time,
    rainMmH: rainArr[i] !== null && rainArr[i] !== undefined ? Math.max(0, rainArr[i]!) : null,
    cloudCoverPct: cloudArr[i] ?? null,
  }));

  return { location, hours: hoursList };
}

export interface CycloneData {
  location: Location;
  time: string;
  pressureHpa: number | null;
  windSpeedKmh: number | null;
  gustSpeedKmh: number | null;
  windDirDeg: number | null;
  waveHeightM: number | null;
  swellHeightM: number | null;
  wavePeriodS: number | null;
  rainMmH: number | null;
  hours: Array<{
    time: string;
    pressureHpa: number | null;
    windSpeedKmh: number | null;
    gustSpeedKmh: number | null;
    windDirDeg: number | null;
    waveHeightM: number | null;
    swellHeightM: number | null;
    wavePeriodS: number | null;
    rainMmH: number | null;
  }>;
}

export async function fetchCycloneData(location: Location, hours: number = 48): Promise<CycloneData> {
  const from = nowISOHour();
  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: CYCLONE_VARS,
    time: { from, interval: '1h', repeat: hours },
  });

  const v = data.variables;
  const times = data.dimensions.time.data;
  const getArr = (key: string): Array<number | null> => v[key]?.data ?? [];

  const pressArr = getArr('air.pressure.at-sea-level');
  const windArr = getArr('wind.speed.at-10m');
  const gustArr = getArr('wind.speed.gust.at-10m');
  const dirArr = getArr('wind.direction.at-10m');
  const waveArr = getArr('wave.height');
  const swellArr = getArr('wave.height.primary-swell');
  const periodArr = getArr('wave.period.peak');
  const rainArr = getArr('precipitation.rate');

  const hoursList = times.map((time, i) => ({
    time,
    pressureHpa: pressArr[i] !== null && pressArr[i] !== undefined ? pressArr[i]! / 100 : null,
    windSpeedKmh: windArr[i] !== null && windArr[i] !== undefined ? windArr[i]! * 3.6 : null,
    gustSpeedKmh: gustArr[i] !== null && gustArr[i] !== undefined ? gustArr[i]! * 3.6 : null,
    windDirDeg: dirArr[i] ?? null,
    waveHeightM: waveArr[i] ?? null,
    swellHeightM: swellArr[i] ?? null,
    wavePeriodS: periodArr[i] ?? null,
    rainMmH: rainArr[i] !== null && rainArr[i] !== undefined ? Math.max(0, rainArr[i]!) : null,
  }));

  const current = hoursList[0] ?? {
    pressureHpa: null, windSpeedKmh: null, gustSpeedKmh: null,
    windDirDeg: null, waveHeightM: null, swellHeightM: null,
    wavePeriodS: null, rainMmH: null,
  };

  return {
    location,
    time: times[0] ?? from,
    ...current,
    hours: hoursList,
  };
}

export interface PressureTrend {
  location: Location;
  currentHpa: number | null;
  readings: Array<{ time: string; pressureHpa: number | null }>;
  trend: {
    changePerHour: number | null;
    change3h: number | null;
    change6h: number | null;
    direction: 'falling-rapidly' | 'falling' | 'steady' | 'rising' | 'rising-rapidly' | 'unknown';
    severity: string;
  };
}

export async function fetchPressureTrend(location: Location): Promise<PressureTrend> {
  // Fetch 12h past + 12h future for trend analysis
  const now = new Date();
  now.setMinutes(0, 0, 0);
  const pastStart = new Date(now.getTime() - 12 * 60 * 60 * 1000);
  const from = pastStart.toISOString().replace(/\.\d{3}Z$/, 'Z');

  const data = await queryPointTime({
    points: [{ lon: location.lon, lat: location.lat }],
    variables: ['air.pressure.at-sea-level'],
    time: { from, interval: '1h', repeat: 24 },
  });

  const times = data.dimensions.time.data;
  const pressArr = data.variables['air.pressure.at-sea-level']?.data ?? [];

  const readings = times.map((time, i) => ({
    time,
    pressureHpa: pressArr[i] !== null && pressArr[i] !== undefined ? pressArr[i]! / 100 : null,
  }));

  // Current is at index 12 (12h into the 24h window)
  const currentIdx = Math.min(12, readings.length - 1);
  const currentHpa = readings[currentIdx]?.pressureHpa ?? null;

  // Calculate changes
  let changePerHour: number | null = null;
  let change3h: number | null = null;
  let change6h: number | null = null;

  if (currentIdx >= 1 && readings[currentIdx]?.pressureHpa !== null && readings[currentIdx - 1]?.pressureHpa !== null) {
    changePerHour = readings[currentIdx].pressureHpa! - readings[currentIdx - 1].pressureHpa!;
  }
  if (currentIdx >= 3 && readings[currentIdx]?.pressureHpa !== null && readings[currentIdx - 3]?.pressureHpa !== null) {
    change3h = readings[currentIdx].pressureHpa! - readings[currentIdx - 3].pressureHpa!;
  }
  if (currentIdx >= 6 && readings[currentIdx]?.pressureHpa !== null && readings[currentIdx - 6]?.pressureHpa !== null) {
    change6h = readings[currentIdx].pressureHpa! - readings[currentIdx - 6].pressureHpa!;
  }

  // Classify trend
  let direction: PressureTrend['trend']['direction'] = 'unknown';
  let severity = '';
  if (change3h !== null) {
    const rate = change3h / 3;
    if (rate <= -3) { direction = 'falling-rapidly'; severity = 'DANGER: Rapid pressure drop (>3 hPa/hr) — severe storm/cyclone intensification'; }
    else if (rate <= -1) { direction = 'falling'; severity = 'Pressure falling — storm approaching'; }
    else if (rate < 1) { direction = 'steady'; severity = 'Pressure stable'; }
    else if (rate < 3) { direction = 'rising'; severity = 'Pressure rising — conditions improving'; }
    else { direction = 'rising-rapidly'; severity = 'Rapid pressure rise — strong wind shift possible'; }
  }

  if (currentHpa !== null && currentHpa < 990) {
    severity += (severity ? '. ' : '') + `WARNING: Pressure ${currentHpa.toFixed(0)} hPa is in tropical cyclone territory (<990 hPa)`;
  }

  return {
    location,
    currentHpa,
    readings,
    trend: { changePerHour, change3h, change6h, direction, severity },
  };
}

export interface WarningsResult {
  source: string;
  fetchedAt: string;
  warnings: Array<{
    type: string;
    level: string;
    areas: string;
    description: string;
    timing: string;
  }>;
  outlook: string;
  raw: string;
}

export async function scrapeWarnings(): Promise<WarningsResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  const fetchedAt = new Date().toISOString();

  try {
    const response = await fetch('https://www.metservice.com/warnings/home', {
      headers: { 'User-Agent': 'MetService-NZ-Skill/1.0' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`MetService warnings page: ${response.status} ${response.statusText}`);
    }

    const html = await response.text();

    // Extract warnings from the HTML
    const warnings: WarningsResult['warnings'] = [];

    // Look for warning cards/sections - MetService uses structured warning blocks
    const warningPatterns = [
      /(?:Red|Orange|Yellow)\s+Warning[^<]*<[^>]*>([^<]*)/gi,
      /(?:Severe|Heavy|Strong)\s+(?:Weather|Wind|Rain|Thunderstorm)[^<]*(?:<[^>]*>)*([^<]*)/gi,
      /class="[^"]*warning[^"]*"[^>]*>([^<]*)/gi,
    ];

    // Extract text content for analysis
    const textContent = html
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    // Look for warning-related content blocks
    const warningKeywords = ['warning', 'watch', 'advisory', 'alert', 'severe', 'cyclone', 'tropical'];
    const sentences = textContent.split(/[.!]\s+/);
    const relevantSentences = sentences.filter(s =>
      warningKeywords.some(kw => s.toLowerCase().includes(kw))
    );

    // Parse structured warnings if found
    const warningBlockRegex = /(Red|Orange|Yellow)\s+(Warning|Watch|Advisory)[:\s]+([^.]+)/gi;
    let match;
    while ((match = warningBlockRegex.exec(textContent)) !== null) {
      warnings.push({
        type: match[2],
        level: match[1],
        areas: '',
        description: match[3].trim(),
        timing: '',
      });
    }

    // If no structured warnings found, check for general severe weather text
    if (warnings.length === 0) {
      const severeRegex = /(?:severe weather|tropical cyclone|heavy rain|strong wind|storm)[^.]+/gi;
      while ((match = severeRegex.exec(textContent)) !== null) {
        warnings.push({
          type: 'Alert',
          level: 'Info',
          areas: '',
          description: match[0].trim(),
          timing: '',
        });
      }
    }

    // Extract outlook
    const outlookMatch = textContent.match(/outlook[:\s]+([^.]+(?:\.[^.]+){0,2})/i);
    const outlook = outlookMatch ? outlookMatch[1].trim() : '';

    return {
      source: 'https://www.metservice.com/warnings/home',
      fetchedAt,
      warnings,
      outlook,
      raw: relevantSentences.slice(0, 20).join('. '),
    };
  } finally {
    clearTimeout(timeout);
  }
}

// Quick self-test
async function main() {
  const loc = LOCATIONS.auckland;
  console.log(`Testing MetOcean API for ${loc.name}...`);
  const conditions = await fetchCurrentConditions(loc);
  console.log(`Temperature: ${conditions.tempC?.toFixed(1) ?? 'N/A'}°C`);
  console.log(`Wind: ${conditions.windSpeedKmh?.toFixed(0) ?? 'N/A'} km/h`);
  console.log(`Rain: ${conditions.rainMmH?.toFixed(1) ?? 'N/A'} mm/h`);
  console.log('OK');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
