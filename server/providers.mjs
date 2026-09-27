export { providerAvailability } from './providers/status.mjs';

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
  if (!process.env.TUNIU_API_KEY && process.env.TUNIU_USE_OAUTH !== '1') return [];
  const { searchTuniuTransport: search } = await import('./providers/ota.mjs');
  return search(...args);
}

export async function searchAttractionProducts(...args) {
  const { searchAttractionProducts: search } = await import('./providers/ota.mjs');
  return search(...args);
}
