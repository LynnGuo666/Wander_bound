import { CITY_CATALOG } from '../../../shared/catalog.mjs';
import { toolError } from '../definitions.mjs';
import { attachDining, planInvariant } from '../plan-output.mjs';

export async function searchAttractions(ctx, args = {}) {
  const { state, providers, providerPriority = {}, warnings } = ctx;
  if (!state.plan) { return toolError('prerequisite', '请先调用 draft_plan'); }
  const selected = state.plan.itinerary.flatMap(day => day.stops.map(stop => ({ ...stop, visitDate: day.date })));
  try {
    const found = typeof providers.searchAttractionProducts === 'function'
      ? await providers.searchAttractionProducts(state.destination, selected) : [];
    const names = new Set(selected.map(place => place.name));
    const offers = Array.isArray(found) ? found.filter(item => item?.provider && names.has(item.name)
      && (item.price === null || (Number.isFinite(item.price) && item.price >= 0))
      && (!item.bookingUrl || /^https:\/\//.test(item.bookingUrl))).slice(0, 60) : [];
    const order = providerPriority.attractions || [];
    const rank = item => {
      const source = item.sourceId || (/飞猪/.test(item.provider) ? 'flyai' : /途牛/.test(item.provider) ? 'tuniu' : '');
      const index = order.indexOf(source);
      return index < 0 ? order.length : index;
    };
    offers.sort((a, b) => rank(a) - rank(b));
    state.plan = { ...state.plan, attractionOffers: offers };
    state.providerStatus.attractions = { configured: typeof providers.searchAttractionProducts === 'function', result: offers.length ? 'ok' : '本次无景区产品', label: '飞猪/途牛景区产品' };
  } catch (error) {
    state.plan = { ...state.plan, attractionOffers: [] };
    state.providerStatus.attractions = { configured: true, error: true, result: String(error.message || '查询失败').slice(0, 160), label: '飞猪/途牛景区产品' };
    warnings.push('景区产品查询失败');
  }
  state.attractionsDone = true;
  return { ok: true, products: state.plan.attractionOffers.map(item => ({ name: item.name, provider: item.provider, productName: item.productName, price: item.price, priceDate: item.priceDate })) };
}

export async function searchDining(ctx, args = {}) {
  const { state, providers, memory, warnings } = ctx;
  if (!state.plan) { return toolError('prerequisite', '请先调用 draft_plan'); }
  try {
    const anchors = state.plan.itinerary.map(day => ({ ...day.stops.at(-1), day: day.day }))
      .filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lng));
    const found = await providers.searchAmapDining(state.destination, anchors);
    const candidates = Array.isArray(found) ? found.filter(item => item?.id && item.name && Number.isFinite(item.lat) && Number.isFinite(item.lng)
      && Number.isInteger(item.day) && item.day >= 1 && item.day <= state.days && item.source)
      .map(item => ({ ...item, rating: Number.isFinite(item.rating) && item.rating > 0 && item.rating <= 5 ? item.rating : null,
        averageCost: Number.isFinite(item.averageCost) && item.averageCost > 0 ? item.averageCost : null,
        photos: Array.isArray(item.photos) ? item.photos.filter(photo => /^https:\/\//.test(photo?.url || '') && photo.kind === 'poi-photo').slice(0, 2) : [],
        sourceRecords: Array.isArray(item.sourceRecords) ? item.sourceRecords
          .filter(record => record?.provider && record.placeId && record.kind === 'place-data').slice(0, 3) : [] })) : [];
    state.plan = attachDining(state.plan, candidates, memory);
    state.providerStatus.dining = { configured: Boolean(state.providerStatus.amap?.configured), result: state.plan.dining.length ? 'ok' : '本次无可核实餐饮结果', label: '高德餐饮 POI' };
  } catch (error) {
    state.plan = attachDining(state.plan, [], memory);
    state.providerStatus.dining = { configured: Boolean(state.providerStatus.amap?.configured), result: error.message, error: true, label: '高德餐饮 POI' };
    warnings.push('餐饮查询失败');
  }
  state.diningDone = true;
  return { ok: true, suggestions: state.plan.dining.map(item => ({ id: item.id, name: item.name, day: item.day, rating: item.rating, averageCost: item.averageCost, source: item.source })) };
}

export async function exploreGround(ctx, args = {}) {
  const { state, providers, memory, warnings } = ctx;
  if (!state.plan) { return toolError('prerequisite', '请先调用 draft_plan'); }
  try {
    const enriched = await providers.enrichRoutes(state.plan);
    const available = [...(CITY_CATALOG[state.destination]?.places || []), ...state.places];
    if (planInvariant(enriched, memory, available)) throw new Error('实时路线导致时刻冲突');
    const stopNames = new Set(enriched.itinerary.flatMap(day => day.stops.map(stop => stop.name)));
    const journeys = Array.isArray(enriched.groundJourneys) ? enriched.groundJourneys
      .filter(item => Number.isInteger(item.day) && item.day >= 1 && item.day <= state.days && stopNames.has(item.to)
        && Number.isFinite(item.minutes) && item.minutes > 0 && item.source && ['walk', 'transit'].includes(item.mode))
      .map(item => ({ ...item, imagery: { status: 'check-on-device', provider: 'Apple MapKit Look Around' } })) : [];
    state.plan = { ...enriched, groundJourneys: journeys };
    state.providerStatus.ground = { configured: Boolean(state.providerStatus.amap?.configured), result: state.plan.groundJourneys.length ? 'ok' : '本次无可核实路线', label: '高德步行与公交' };
  } catch (error) {
    state.plan = { ...state.plan, groundJourneys: [] };
    state.providerStatus.ground = { configured: Boolean(state.providerStatus.amap?.configured), result: error.message, error: true, label: '高德步行与公交' };
    warnings.push(error.message === '实时路线导致时刻冲突' ? error.message : '路线服务失败，保留估算交通时间');
  }
  state.groundDone = true;
  return { ok: true, verifiedLegs: state.plan.groundJourneys.length, legs: state.plan.groundJourneys.slice(0, 12).map(item => ({ day: item.day, from: item.from, to: item.to, minutes: item.minutes, mode: item.mode, source: item.source })) };
}
