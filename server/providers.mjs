import { providerAvailability } from './providers/status.mjs';
export { providerAvailability };

// A request owns its credentials. Never mutate process.env: concurrent users must remain isolated.
export function createRequestProviders(credentials = {}) {
  const key = (name, envName) => credentials[name] || process.env[envName];
  const runner = async (binary, args) => {
    const { runCli } = await import('./ota/run-cli.mjs');
    return runCli(binary, args, { credentials });
  };
  return {
    providerAvailability: () => providerAvailability(credentials),
    reverseLocation: async location => key('amap', 'AMAP_WEB_KEY') ? (await import('./providers/amap.mjs')).reverseLocation(location, key('amap', 'AMAP_WEB_KEY')) : null,
    searchAmapPlaces: async city => key('amap', 'AMAP_WEB_KEY') ? (await import('./providers/amap.mjs')).searchAmapPlaces(city, key('amap', 'AMAP_WEB_KEY')) : [],
    searchAmapDining: async (city, anchors) => key('amap', 'AMAP_WEB_KEY') ? (await import('./providers/amap.mjs')).searchAmapDining(city, anchors, key('amap', 'AMAP_WEB_KEY')) : [],
    routeMinutes: async (origin, destination, city) => key('amap', 'AMAP_WEB_KEY') ? (await import('./providers/amap.mjs')).routeMinutes(origin, destination, city, key('amap', 'AMAP_WEB_KEY')) : null,
    enrichRoutes: async plan => key('amap', 'AMAP_WEB_KEY') ? (await import('./providers/amap.mjs')).enrichRoutes(plan, key('amap', 'AMAP_WEB_KEY')) : plan,
    searchDidaHotels: async (...args) => key('dida', 'DIDA_API_KEY') ? (await import('./providers/dida.mjs')).searchDidaHotels(...args, key('dida', 'DIDA_API_KEY')) : [],
    searchDuffelFlights: async (...args) => key('duffel', 'DUFFEL_API_KEY') ? (await import('./providers/duffel.mjs')).searchDuffelFlights(...args, key('duffel', 'DUFFEL_API_KEY')) : [],
    searchFlyaiTransport: async (...args) => (await import('./providers/ota.mjs')).searchFlyaiTransport(...args, runner),
    searchTuniuTransport: async (...args) => (await import('./providers/ota.mjs')).searchTuniuTransport(...args, runner, Boolean(key('tuniu', 'TUNIU_API_KEY'))),
    searchAttractionProducts: async (...args) => (await import('./providers/ota.mjs')).searchAttractionProducts(...args, runner, Boolean(key('tuniu', 'TUNIU_API_KEY'))),
    searchRailTickets: async (origin, destination, date) => (await import('./providers/rail12306.mjs')).searchRailTickets(origin, destination, date),
  };
}


export async function reverseLocation(location) {
  if (!process.env.AMAP_WEB_KEY) return null;
  const { reverseLocation: search } = await import('./providers/amap.mjs');
  return search(location);
}

export async function searchAmapPlaces(city) {
  if (!process.env.AMAP_WEB_KEY) return [];
  const { searchAmapPlaces: search } = await import('./providers/amap.mjs');
  return search(city);
}

export async function searchAmapDining(city, anchors) {
  if (!process.env.AMAP_WEB_KEY) return [];
  const { searchAmapDining: search } = await import('./providers/amap.mjs');
  return search(city, anchors);
}

export async function routeMinutes(origin, destination, city) {
  if (!process.env.AMAP_WEB_KEY) return null;
  const { routeMinutes: search } = await import('./providers/amap.mjs');
  return search(origin, destination, city);
}

export async function enrichRoutes(plan) {
  if (!process.env.AMAP_WEB_KEY) return plan;
  const { enrichRoutes: enrich } = await import('./providers/amap.mjs');
  return enrich(plan);
}

export async function searchDidaHotels(...args) {
  if (!process.env.DIDA_API_KEY) return [];
  const { searchDidaHotels: search } = await import('./providers/dida.mjs');
  return search(...args);
}

export async function searchDuffelFlights(...args) {
  if (!process.env.DUFFEL_API_KEY) return [];
  const { searchDuffelFlights: search } = await import('./providers/duffel.mjs');
  return search(...args);
}

export async function searchFlyaiTransport(...args) {
  const { searchFlyaiTransport: search } = await import('./providers/ota.mjs');
  return search(...args);
}

export async function searchTuniuTransport(...args) {
  if (!process.env.TUNIU_API_KEY) return [];
  const { searchTuniuTransport: search } = await import('./providers/ota.mjs');
  return search(...args);
}

export async function searchAttractionProducts(...args) {
  const { searchAttractionProducts: search } = await import('./providers/ota.mjs');
  return search(...args);
}

export async function searchRailTickets(...args) {
  if (!process.env.TRAVEL_12306_MCP_URL) return [];
  const { searchRailTickets: search } = await import('./providers/rail12306.mjs');
  return search(...args);
}
