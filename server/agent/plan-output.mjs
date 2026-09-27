import { CITY_CATALOG } from '../../shared/catalog.mjs';
import { kmBetween } from '../../shared/planner.mjs';

export function planInvariant(plan, memory, available) {
  if (!plan || plan.itinerary.length !== plan.days) return '行程天数不正确';
  const allowed = new Set(available.map(place => place.id));
  const seen = new Set();
  for (const day of plan.itinerary) {
    let previousEnd = 0;
    for (const stop of day.stops) {
      if (!allowed.has(stop.id)) return `地点 ${stop.id} 不在已核实候选中`;
      if (seen.has(stop.id)) return `地点 ${stop.id} 重复`;
      if (memory.visitedPlaces.some(place => place.id === stop.id || (place.name === stop.name && place.city === plan.destination))) return `地点 ${stop.id} 已去过`;
      if (!/^\d{2}:\d{2}$/.test(stop.start) || Number(stop.start.slice(0, 2)) >= 24) return '行程时间无效';
      if (!Number.isFinite(stop.duration) || stop.duration <= 0) return '景点游玩时长无效';
      const startMinutes = Number(stop.start.slice(0, 2)) * 60 + Number(stop.start.slice(3, 5));
      if (Number(stop.start.slice(3, 5)) >= 60 || startMinutes < previousEnd) return '景点时间重叠或无效';
      if (startMinutes + stop.duration > 24 * 60) return '景点游玩跨越午夜';
      if (stop.time === 'afternoon' && startMinutes < 12 * 60 + 30) return '下午地点安排过早';
      if (stop.time === 'evening' && startMinutes < 17 * 60) return '傍晚地点安排过早';
      seen.add(stop.id);
      previousEnd = startMinutes + stop.duration;
    }
  }
  return null;
}

export function attachDining(plan, candidates, memory) {
  const used = new Set();
  const itinerary = plan.itinerary.map(day => {
    const anchor = day.stops.at(-1) || day.stops[0];
    if (!anchor) return { ...day, diningSuggestions: [] };
    const chosen = candidates
      .filter(item => item.day === day.day && !used.has(item.id))
      .filter(item => !memory.visitedPlaces.some(visited => visited.id === item.id || (visited.name === item.name && visited.city === plan.destination)))
      .filter(item => kmBetween(anchor, item) <= 2)
      .sort((a, b) => {
        const score = item => {
          const distanceKm = kmBetween(anchor, item);
          const ratingBonus = Number.isFinite(item.rating) ? (item.rating - 3.5) * 1.5 : 0;
          const cuisineBonus = memory.cuisinePreferences.some(value => item.type?.includes(value)) ? 1.2 : 0;
          const budgetPenalty = memory.diningBudgetPerPerson && item.averageCost > memory.diningBudgetPerPerson
            ? Math.min(3, (item.averageCost - memory.diningBudgetPerPerson) / Math.max(30, memory.diningBudgetPerPerson)) : 0;
          return ratingBonus + cuisineBonus - distanceKm * 0.7 - budgetPenalty;
        };
        return score(b) - score(a) || kmBetween(anchor, a) - kmBetween(anchor, b);
      })[0];
    if (!chosen) return { ...day, diningSuggestions: [] };
    used.add(chosen.id);
    return { ...day, diningSuggestions: [{ ...chosen, nearStopId: anchor.id, distanceMetersApprox: Math.round(kmBetween(anchor, chosen) * 1000) }] };
  });
  return { ...plan, itinerary, dining: itinerary.flatMap(day => day.diningSuggestions) };
}

export function buildCapabilityStatus(enriched, state) {
  return {
    flights: { status: [...enriched.flights, ...enriched.returnFlights].some(item => Number.isFinite(item.totalPrice)) ? 'offers_found' : enriched.flights.length || enriched.returnFlights.length ? 'schedules_found' : (['flyai', 'tuniu', 'duffel'].some(id => state.providerStatus[id]?.error) ? 'failed' : ['flyai', 'tuniu', 'duffel'].some(id => state.providerStatus[id]?.configured) ? 'empty' : 'unavailable'),
      outboundCount: enriched.flights.length, returnCount: enriched.returnFlights.length, source: [...new Set([...enriched.flights, ...enriched.returnFlights].map(offer => offer.provider))].join('、') || null },
    trains: { status: [...enriched.trains, ...enriched.returnTrains].some(item => Number.isFinite(item.totalPrice)) ? 'offers_found' : enriched.trains.length || enriched.returnTrains.length ? 'schedules_found' : (['flyai', 'tuniu'].some(id => state.providerStatus[id]?.error) ? 'failed' : ['flyai', 'tuniu'].some(id => state.providerStatus[id]?.configured) ? 'empty' : 'unavailable'),
      outboundCount: enriched.trains.length, returnCount: enriched.returnTrains.length, source: [...new Set([...enriched.trains, ...enriched.returnTrains].map(offer => offer.provider))].join('、') || null },
    attractions: { status: enriched.attractionOffers?.length ? 'products_found' : 'planned', placeCount: enriched.itinerary.reduce((total, day) => total + day.stops.length, 0), productCount: enriched.attractionOffers?.length || 0,
      source: enriched.attractionOffers?.length ? [...new Set(enriched.attractionOffers.map(item => item.provider))].join('、') : CITY_CATALOG[state.destination] ? '编辑目录' : '高德 POI' },
    lodging: { status: enriched.hotels.length ? 'offers_found' : (state.providerStatus.dida?.error ? 'failed' : 'area_only'), offerCount: enriched.hotels.length,
      source: enriched.hotels.length ? '道旅' : '行程地点分布' },
    food: { status: enriched.dining.length ? 'places_found' : (state.providerStatus.dining?.error ? 'failed' : state.providerStatus.dining?.configured ? 'empty' : 'unavailable'),
      placeCount: enriched.dining.length, source: '高德餐饮 POI' },
    reviews: { status: 'unavailable', source: null, reviewCount: 0 },
    groundExploration: { status: enriched.groundJourneys.length ? 'routes_found' : (state.providerStatus.ground?.error ? 'failed' : 'estimated'),
      legCount: enriched.groundJourneys.length, imageryStatus: 'check-on-device', source: enriched.groundJourneys.length ? '高德路线' : '直线距离估算' },
  };
}
