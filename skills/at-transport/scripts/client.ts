import { pathToFileURL } from 'node:url';

const BASE_URL = 'https://api.at.govt.nz';
const API_KEY = process.env.AT_API_KEY ?? 'de42128902d24a7a86a013633f7aa832';
const DEFAULT_TIMEOUT_MS = 15_000;

// --- Types ---

export interface Stop {
  stop_id: string;
  stop_code: string;
  stop_name: string;
  stop_lat: number;
  stop_lon: number;
  location_type: number;
  parent_station?: string;
  platform_code?: string;
  wheelchair_boarding?: number;
}

export interface Route {
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  route_type: number;
  route_color?: string;
  route_text_color?: string;
  agency_id: string;
}

export interface AlertTranslation {
  text: string;
  language: string;
}

export interface AlertEntity {
  route_id?: string;
  stop_id?: string;
}

export interface ServiceAlert {
  id: string;
  active_period: Array<{ start: number; end: number }>;
  informed_entity: AlertEntity[];
  cause: string;
  effect: string;
  severity_level: string;
  header_text: string;
  description_text: string;
}

export interface TripDescriptor {
  trip_id: string;
  start_time: string;
  start_date: string;
  schedule_relationship: number;
  route_id: string;
  direction_id: number;
}

export interface StopTimeEvent {
  delay?: number;
  time?: number;
  uncertainty?: number;
}

export interface StopTimeUpdate {
  stop_sequence: number;
  arrival?: StopTimeEvent;
  departure?: StopTimeEvent;
  stop_id: string;
  schedule_relationship: number;
}

export interface TripUpdate {
  id: string;
  trip: TripDescriptor;
  stop_time_update: StopTimeUpdate;
  vehicle?: { id: string; label: string };
  timestamp: number;
  delay: number;
}

export interface VehiclePosition {
  id: string;
  position: {
    latitude: number;
    longitude: number;
    bearing?: string;
    speed: number;
  };
  trip?: TripDescriptor;
  vehicle: { id: string; label: string };
  timestamp: number;
}

export interface Departure {
  route_id: string;
  route_short_name: string;
  route_type: number;
  trip_id: string;
  stop_id: string;
  stop_name: string;
  direction_id: number;
  scheduled_time: string;
  expected_time: string | null;
  delay_seconds: number;
  vehicle_id: string | null;
  vehicle_label: string | null;
}

// --- Fetch helpers ---

async function getJson<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      headers: {
        Accept: 'application/json',
        'Ocp-Apim-Subscription-Key': API_KEY,
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`AT API ${path}: ${response.status} ${response.statusText}`);
    }

    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

// --- GTFS Static ---

let stopsCache: Stop[] | null = null;
let routesCache: Map<string, Route> | null = null;

export async function getStops(): Promise<Stop[]> {
  if (stopsCache) return stopsCache;
  const data = await getJson<{ data: Array<{ id: string; attributes: Stop }> }>('/gtfs/v3/stops');
  stopsCache = data.data.map((s) => s.attributes);
  return stopsCache;
}

export async function getStop(stopId: string): Promise<Stop> {
  const data = await getJson<{ data: { attributes: Stop } }>(`/gtfs/v3/stops/${stopId}`);
  return data.attributes;
}

export async function getRoutesMap(): Promise<Map<string, Route>> {
  if (routesCache) return routesCache;
  const data = await getJson<{ data: Array<{ id: string; attributes: Route }> }>('/gtfs/v3/routes');
  routesCache = new Map(data.data.map((r) => [r.attributes.route_id, r.attributes]));
  return routesCache;
}

export async function getRoute(routeId: string): Promise<Route> {
  const data = await getJson<{ data: { attributes: Route } }>(`/gtfs/v3/routes/${routeId}`);
  return data.attributes;
}

export async function searchStops(query: string): Promise<Stop[]> {
  const stops = await getStops();
  const lower = query.toLowerCase();
  return stops.filter(
    (s) =>
      s.stop_name.toLowerCase().includes(lower) ||
      s.stop_code.toLowerCase() === lower ||
      s.stop_id.toLowerCase() === lower,
  );
}

export async function nearbyStops(lat: number, lon: number, radiusMeters: number = 500): Promise<Array<Stop & { distance_m: number }>> {
  const stops = await getStops();
  const results: Array<Stop & { distance_m: number }> = [];

  for (const stop of stops) {
    const dist = haversineMeters(lat, lon, stop.stop_lat, stop.stop_lon);
    if (dist <= radiusMeters) {
      results.push({ ...stop, distance_m: Math.round(dist) });
    }
  }

  return results.sort((a, b) => a.distance_m - b.distance_m);
}

function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6_371_000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// --- GTFS-RT Realtime ---

interface RealtimeResponse<T> {
  status: string;
  response: {
    header: { timestamp: number };
    entity: T[];
  };
}

interface RawAlertEntity {
  id: string;
  alert: {
    active_period: Array<{ start: number; end: number }>;
    informed_entity: AlertEntity[];
    cause: string;
    effect: string;
    severity_level: string;
    header_text: { translation: AlertTranslation[] };
    description_text: { translation: AlertTranslation[] };
  };
}

interface RawTripUpdateEntity {
  id: string;
  trip_update: {
    trip: TripDescriptor;
    stop_time_update: StopTimeUpdate;
    vehicle?: { id: string; label: string };
    timestamp: number;
    delay: number;
  };
}

interface RawVehicleEntity {
  id: string;
  vehicle: {
    position: { latitude: number; longitude: number; bearing?: string; speed: number };
    trip?: TripDescriptor;
    vehicle: { id: string; label: string };
    timestamp: number;
  };
}

export async function getServiceAlerts(): Promise<ServiceAlert[]> {
  const data = await getJson<RealtimeResponse<RawAlertEntity>>('/realtime/legacy/servicealerts');
  return data.response.entity.map((e) => ({
    id: e.id,
    active_period: e.alert.active_period,
    informed_entity: e.alert.informed_entity,
    cause: e.alert.cause,
    effect: e.alert.effect,
    severity_level: e.alert.severity_level ?? 'UNKNOWN',
    header_text: e.alert.header_text?.translation?.[0]?.text ?? '',
    description_text: e.alert.description_text?.translation?.[0]?.text ?? '',
  }));
}

export async function getTripUpdates(): Promise<TripUpdate[]> {
  const data = await getJson<RealtimeResponse<RawTripUpdateEntity>>('/realtime/legacy/tripupdates');
  return data.response.entity
    .filter((e) => e.trip_update?.stop_time_update?.stop_id)
    .map((e) => ({
      id: e.id,
      trip: e.trip_update.trip,
      stop_time_update: e.trip_update.stop_time_update,
      vehicle: e.trip_update.vehicle,
      timestamp: e.trip_update.timestamp,
      delay: e.trip_update.delay,
    }));
}

export async function getVehiclePositions(): Promise<VehiclePosition[]> {
  const data = await getJson<RealtimeResponse<RawVehicleEntity>>('/realtime/legacy/vehiclelocations');
  return data.response.entity.map((e) => ({
    id: e.id,
    position: e.vehicle.position,
    trip: e.vehicle.trip,
    vehicle: e.vehicle.vehicle,
    timestamp: e.vehicle.timestamp,
  }));
}

// --- Composite: Departures ---

async function resolveStopIds(stopInput: string): Promise<Set<string>> {
  const stops = await getStops();
  const ids = new Set<string>();

  // Find the stop by ID or code
  const match = stops.find(
    (s) => s.stop_id === stopInput || s.stop_code === stopInput,
  );

  if (match) {
    ids.add(match.stop_id);
    // If it's a parent station (location_type=1), include child stops
    if (match.location_type === 1) {
      for (const s of stops) {
        if (s.parent_station === match.stop_id) {
          ids.add(s.stop_id);
        }
      }
    }
    // Also include sibling stops under the same parent
    if (match.parent_station) {
      ids.add(match.parent_station);
      for (const s of stops) {
        if (s.parent_station === match.parent_station) {
          ids.add(s.stop_id);
        }
      }
    }
  }

  return ids;
}

export async function getDepartures(stopInput: string): Promise<{ stop: Stop; departures: Departure[] }> {
  const stops = await getStops();

  // Resolve the stop
  const match = stops.find(
    (s) => s.stop_id === stopInput || s.stop_code === stopInput,
  );
  if (!match) {
    throw new Error(`Stop not found: ${stopInput}. Use 'stops <query>' to search.`);
  }

  const stopIds = await resolveStopIds(stopInput);
  const [tripUpdates, routesMap] = await Promise.all([getTripUpdates(), getRoutesMap()]);

  // Build a stop name lookup
  const stopNameMap = new Map(stops.map((s) => [s.stop_id, s.stop_name]));

  const departures: Departure[] = [];

  for (const tu of tripUpdates) {
    const stu = tu.stop_time_update;
    if (!stopIds.has(stu.stop_id)) continue;

    const route = routesMap.get(tu.trip.route_id);
    const departureTime = stu.departure?.time ?? stu.arrival?.time;
    const scheduledDelay = stu.departure?.delay ?? stu.arrival?.delay ?? tu.delay;

    departures.push({
      route_id: tu.trip.route_id,
      route_short_name: route?.route_short_name ?? tu.trip.route_id,
      route_type: route?.route_type ?? 3,
      trip_id: tu.trip.trip_id,
      stop_id: stu.stop_id,
      stop_name: stopNameMap.get(stu.stop_id) ?? stu.stop_id,
      direction_id: tu.trip.direction_id,
      scheduled_time: tu.trip.start_time,
      expected_time: departureTime ? new Date(departureTime * 1000).toISOString() : null,
      delay_seconds: scheduledDelay,
      vehicle_id: tu.vehicle?.id ?? null,
      vehicle_label: tu.vehicle?.label?.trim() ?? null,
    });
  }

  // Sort by expected time, then scheduled time
  departures.sort((a, b) => {
    const ta = a.expected_time ? Date.parse(a.expected_time) : 0;
    const tb = b.expected_time ? Date.parse(b.expected_time) : 0;
    if (ta && tb) return ta - tb;
    return a.scheduled_time.localeCompare(b.scheduled_time);
  });

  return { stop: match, departures };
}

// --- Composite: Network status ---

export interface NetworkStatus {
  timestamp: string;
  alerts_count: number;
  alerts_by_severity: Record<string, number>;
  active_trips: number;
  active_vehicles: number;
  delayed_trips: number;
  avg_delay_seconds: number;
  on_time_percentage: number;
}

export async function getNetworkStatus(): Promise<NetworkStatus> {
  const [alerts, tripUpdates, vehicles] = await Promise.all([
    getServiceAlerts(),
    getTripUpdates(),
    getVehiclePositions(),
  ]);

  const bySeverity: Record<string, number> = {};
  for (const a of alerts) {
    bySeverity[a.severity_level] = (bySeverity[a.severity_level] ?? 0) + 1;
  }

  const activeTripUpdates = tripUpdates.filter((t) => t.trip.schedule_relationship !== 3);
  const delayedTrips = activeTripUpdates.filter((t) => Math.abs(t.delay) > 120);
  const totalDelay = activeTripUpdates.reduce((sum, t) => sum + t.delay, 0);
  const avgDelay = activeTripUpdates.length > 0 ? totalDelay / activeTripUpdates.length : 0;
  const onTime = activeTripUpdates.filter((t) => Math.abs(t.delay) <= 120).length;
  const onTimePct = activeTripUpdates.length > 0 ? (onTime / activeTripUpdates.length) * 100 : 100;

  return {
    timestamp: new Date().toISOString(),
    alerts_count: alerts.length,
    alerts_by_severity: bySeverity,
    active_trips: activeTripUpdates.length,
    active_vehicles: vehicles.length,
    delayed_trips: delayedTrips.length,
    avg_delay_seconds: Math.round(avgDelay),
    on_time_percentage: Math.round(onTimePct * 10) / 10,
  };
}

// --- Route type helpers ---

export function routeTypeIcon(routeType: number): string {
  switch (routeType) {
    case 0: return '🚊'; // Tram
    case 1: return '🚇'; // Subway
    case 2: return '🚆'; // Rail
    case 3: return '🚌'; // Bus
    case 4: return '⛴️';  // Ferry
    default: return '🚍';
  }
}

export function routeTypeName(routeType: number): string {
  switch (routeType) {
    case 0: return 'Tram';
    case 1: return 'Subway';
    case 2: return 'Train';
    case 3: return 'Bus';
    case 4: return 'Ferry';
    default: return 'Transit';
  }
}

async function main() {
  const status = await getNetworkStatus();
  console.log(`Auckland Transport Network Status`);
  console.log(`Active trips: ${status.active_trips}`);
  console.log(`Active vehicles: ${status.active_vehicles}`);
  console.log(`On-time: ${status.on_time_percentage}%`);
  console.log(`Alerts: ${status.alerts_count}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
