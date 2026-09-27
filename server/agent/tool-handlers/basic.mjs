import { CITY_CATALOG } from '../../../shared/catalog.mjs';
import { toolError } from '../definitions.mjs';
import { cleanCity, cleanInterests } from '../request.mjs';

function compactPlaces(places) {
  return places.slice(0, 45).map(place => ({ id: place.id, name: place.name, area: place.area, category: place.category, duration: place.duration }));
}

export async function setTripSpec(ctx, args = {}) {
  const { state, explicitDestination, explicitDays } = ctx;
  if (state.placesDone) { return toolError('spec_locked', '地点查询后不能修改目的地'); }
  const destination = explicitDestination || cleanCity(args.destination || state.destination);
  const days = explicitDays ?? Number(args.days || state.days);
  if (!destination || !Number.isInteger(days) || days < 1 || days > 7) { return toolError('invalid_trip', '目的地或天数无效'); }
  state.destination = destination;
  state.days = days;
  state.desiredInterests = cleanInterests(args.interests).length ? cleanInterests(args.interests) : state.desiredInterests;
  return { ok: true, destination, days, interests: state.desiredInterests };
}

export async function resolveOrigin(ctx, args = {}) {
  const { state, input, providers, warnings } = ctx;
  const lat = Number(input.location?.lat);
  const lng = Number(input.location?.lng);
  if (Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 && input.location && state.providerStatus.amap.configured) {
    try {
      const detected = await providers.reverseLocation({ lat, lng });
      if (detected) { state.originCity = cleanCity(detected); state.locationDetected = true; }
    } catch (error) { warnings.push('位置反查失败，使用手填城市'); state.providerStatus.amap.result = error.message; }
  }
  state.originDone = true;
  return { ok: true, originCity: state.originCity, locationDetected: state.locationDetected };
}

export async function discoverPlaces(ctx, args = {}) {
  const { state, providers, memory, warnings } = ctx;
  if (!state.destination) { return toolError('missing_destination', '请先确定目的地'); }
  const catalog = CITY_CATALOG[state.destination];
  if (!catalog) {
    try {
      const found = await providers.searchAmapPlaces(state.destination);
      state.places = Array.isArray(found) ? found.filter(place => place?.id && Number.isFinite(place.lat) && Number.isFinite(place.lng)) : [];
      state.providerStatus.amap.result = state.places.length ? 'ok' : '本次无地点结果';
    }
    catch (error) { state.providerStatus.amap.result = error.message; state.places = []; warnings.push('地点查询失败'); }
  }
  state.placesDone = true;
  const available = [...(catalog?.places || []), ...state.places]
    .filter(place => place?.id && Number.isFinite(place.lat) && Number.isFinite(place.lng))
    .filter(place => !memory.visitedPlaces.some(visited => visited.id === place.id || (visited.name === place.name && visited.city === state.destination)));
  state.availableCount = available.length;
  return available.length
    ? { ok: true, places: compactPlaces(available), excludedVisitedCount: memory.visitedPlaces.filter(place => place.city === state.destination).length }
    : toolError('no_new_places', `没有可核实的${state.destination}新地点`);
}
