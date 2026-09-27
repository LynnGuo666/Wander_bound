import { DEFAULT_MEMORY } from './catalog.mjs';

export function normalizeMemory(value = {}) {
  return {
    ...DEFAULT_MEMORY,
    ...value,
    hotelBrands: Array.isArray(value.hotelBrands) ? value.hotelBrands.filter(Boolean) : DEFAULT_MEMORY.hotelBrands,
    cuisinePreferences: Array.isArray(value.cuisinePreferences) ? value.cuisinePreferences.filter(Boolean) : [],
    visitedCities: Array.isArray(value.visitedCities) ? value.visitedCities : [],
    visitedPlaces: Array.isArray(value.visitedPlaces) ? value.visitedPlaces : [],
    interests: Array.isArray(value.interests) ? value.interests : DEFAULT_MEMORY.interests,
  };
}

export function kmBetween(a, b) {
  const rad = degrees => degrees * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

function noveltyScore(place, memory, cityVisited, desiredInterests, destination) {
  if (memory.visitedPlaces.some(item => item.id === place.id || (item.name === place.name && item.city === destination))) return -Infinity;
  const interests = desiredInterests.length ? desiredInterests : memory.interests;
  return (interests.includes(place.category) ? 4 : 0) + (cityVisited ? 1 : 0);
}

export function selectPlaces(destination, days, memory, desiredInterests = [], livePlaces = []) {
  const cityVisited = memory.visitedCities.includes(destination);
  const unique = [...new Map(livePlaces.map(place => [place.id || place.name, place])).values()];
  const candidates = unique
    .map(place => ({ ...place, score: noveltyScore(place, memory, cityVisited, desiredInterests, destination) }))
    .filter(place => Number.isFinite(place.score))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, 'zh'));
  if (!candidates.length) return [];
  const chosen = [];
  const target = Math.min(candidates.length, days === 1 ? 2 : days === 2 ? 4 : 4 + (days - 2) * 3);
  const center = centroid(candidates);
  while (chosen.length < target) {
    const last = chosen.at(-1);
    const next = candidates
      .filter(place => !chosen.some(item => item.id === place.id))
      .sort((a, b) => {
        const aGrouping = last ? (a.area === last.area ? 1 : 0) : 0;
        const bGrouping = last ? (b.area === last.area ? 1 : 0) : 0;
        return b.score + bGrouping - kmBetween(b, center) * 0.22 - a.score - aGrouping + kmBetween(a, center) * 0.22;
      })[0];
    if (!next) break;
    chosen.push(next);
  }
  return chosen;
}

function centroid(points) {
  if (!points.length) return null;
  const lat = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
  const lng = points.reduce((sum, point) => sum + point.lng, 0) / points.length;
  return { lat, lng };
}

function shiftDate(iso, days) {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function combinations(items, size, offset = 0, current = [], result = []) {
  if (current.length === size) { result.push([...current]); return result; }
  for (let index = offset; index <= items.length - (size - current.length); index += 1) {
    current.push(items[index]);
    combinations(items, size, index + 1, current, result);
    current.pop();
  }
  return result;
}

function chooseDayPlaces(available, count, anchor, edgeDay, lastDayCenter = null) {
  const subsets = combinations(available, Math.min(count, available.length));
  return subsets.sort((a, b) => {
    const measure = group => {
      let score = group.reduce((sum, place) => sum + (place.score || 0), 0);
      for (let i = 0; i < group.length; i += 1) {
        for (let j = i + 1; j < group.length; j += 1) score -= kmBetween(group[i], group[j]) * 0.46;
        if (anchor) score -= kmBetween(group[i], anchor) * (edgeDay ? 0.19 : 0.04);
        if (lastDayCenter) score -= kmBetween(group[i], lastDayCenter) * 0.55;
      }
      return score;
    };
    return measure(b) - measure(a);
  })[0] || [];
}

function orderDayPlaces(places, anchor) {
  const remaining = [...places];
  const ordered = [];
  let current = anchor;
  while (remaining.length) {
    remaining.sort((a, b) => kmBetween(current, a) - kmBetween(current, b));
    const next = remaining.shift();
    ordered.push(next);
    current = next;
  }
  return ordered;
}

// 行程只做逐日分组与组内顺序；不产出时钟时刻。游玩时长与转场时间
// 没有任何真实数据来源，留空（null）并由能力状态如实标注。
export function buildDays(places, startDate, days, arrivalAt = '') {
  const center = centroid(places);
  const arrivalHour = Number(arrivalAt.slice(11, 13));
  const firstStart = arrivalAt && Number.isFinite(arrivalHour) ? arrivalHour * 60 + Number(arrivalAt.slice(14, 16) || 0) + 90 : 0;
  const counts = Array.from({ length: days }, (_, index) => days === 1 ? 2 : index === 0 || index === days - 1 ? 2 : 3);
  if (firstStart >= 20 * 60) counts[0] = 0;
  else if (arrivalAt && firstStart >= 17 * 60) counts[0] = 1;
  const groups = Array.from({ length: days }, () => []);
  const sequence = days === 1 ? [0] : [0, days - 1, ...Array.from({ length: Math.max(0, days - 2) }, (_, index) => index + 1)];
  let available = [...places];
  for (const [position, index] of sequence.entries()) {
    const balancedCount = Math.min(counts[index], Math.ceil(available.length / (sequence.length - position)));
    const chosen = chooseDayPlaces(available, balancedCount, center, index === 0 || index === days - 1, index === days - 1 ? center : null);
    groups[index] = orderDayPlaces(chosen, center);
    const selectedIds = new Set(chosen.map(place => place.id));
    available = available.filter(place => !selectedIds.has(place.id));
  }
  return groups.map((selected, index) => ({
    day: index + 1,
    date: shiftDate(startDate, index),
    title: selected.length ? `${selected[0].area || '城区'} · 自由探索` : index === 0 ? '抵达与入住' : '留白 · 自由探索',
    stops: selected.map(place => ({ ...place, start: null, travelMinutes: null, travelSource: null })),
  }));
}

// 住宿区域建议从已核实地点的分布推导：取出现最多的区域，以其地点质心为坐标。
export function chooseStayArea(itinerary) {
  const stops = itinerary.flatMap(day => day.stops);
  if (!stops.length) return null;
  const counts = new Map();
  for (const stop of stops) if (stop.area) counts.set(stop.area, (counts.get(stop.area) || 0) + 1);
  const area = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  if (!area) return null;
  const cluster = stops.filter(stop => stop.area === area);
  return { name: area, ...centroid(cluster) };
}

export function rankFlights(flights, memory, providerPriority = []) {
  return flights.map(flight => {
    const departureHour = Number(flight.departureAt?.slice(11, 13));
    const arrivalDate = flight.arrivalAt?.slice(0, 10);
    const departDate = flight.departureAt?.slice(0, 10);
    const redEye = departureHour >= 22 || departureHour < 6 || arrivalDate > departDate;
    const arrivalHour = Number(flight.arrivalAt?.slice(11, 13));
    const lateArrivalCost = Number.isFinite(arrivalHour) ? Math.max(0, arrivalHour - 16) * 80 : 0;
    const score = (Number(flight.totalPrice) || 99999) + (flight.priceComplete === false ? 10000 : 0)
      + (redEye && memory.avoidRedEye ? 100000 : 0) + (flight.stops || 0) * 180 + lateArrivalCost;
    return { ...flight, redEye, score };
  }).sort((a, b) => {
    const rank = item => {
      const index = providerPriority.indexOf(item.sourceId);
      return index < 0 ? providerPriority.length : index;
    };
    return rank(a) - rank(b) || a.score - b.score;
  });
}

export function assemblePlan({ destination, originCity, startDate, days, memory, places = [], flights = [], returnFlights = [], trains = [], returnTrains = [], hotels = [], providerStatus = {}, providerPriority = {}, desiredInterests = [], proposedPlaceIds = [] }) {
  const normalized = normalizeMemory(memory);
  const candidates = selectPlaces(destination, days, normalized, desiredInterests, places);
  const selected = proposedPlaceIds.length
    ? proposedPlaceIds.map(id => places.find(place => place.id === id))
      .filter(place => place && !normalized.visitedPlaces.some(visited => visited.id === place.id || (visited.name === place.name && visited.city === destination)))
    : candidates;
  const rankedFlights = rankFlights(flights, normalized, providerPriority.flights);
  const preferredFlight = rankedFlights.find(flight => !flight.redEye && flight.priceComplete !== false && Number.isFinite(flight.totalPrice));
  const rankedTrains = rankFlights(trains, normalized, providerPriority.trains);
  const preferredTrain = rankedTrains.find(train => !train.redEye && train.priceComplete !== false && Number.isFinite(train.totalPrice));
  const selectedTransportMode = normalized.transportPreference === 'train'
    ? (preferredTrain ? 'train' : preferredFlight ? 'flight' : 'train')
    : (preferredFlight ? 'flight' : preferredTrain ? 'train' : 'flight');
  const selectedArrival = selectedTransportMode === 'flight' ? preferredFlight?.arrivalAt : preferredTrain?.arrivalAt;
  const itinerary = buildDays(selected, startDate, days, selectedArrival || '');
  const stayArea = chooseStayArea(itinerary);
  const endDate = shiftDate(startDate, days - 1);
  const rankedReturnFlights = rankFlights(returnFlights, normalized, providerPriority.flights);
  const rankedReturnTrains = rankFlights(returnTrains, normalized, providerPriority.trains);
  const rankedHotels = [...hotels].sort((a, b) => {
    const brand = hotel => normalized.hotelBrands.some(value => hotel.name?.includes(value)) ? -150 : 0;
    const price = hotel => Number(hotel.totalPrice) || 99999;
    const distance = hotel => stayArea && hotel.lat && hotel.lng ? kmBetween(stayArea, hotel) * 15 : 0;
    return price(a) + brand(a) + distance(a) - price(b) - brand(b) - distance(b);
  });
  return {
    destination, originCity, startDate, endDate, days,
    intro: `为你探索${destination}的新地点。`,
    revisit: normalized.visitedCities.includes(destination),
    skippedPlaces: normalized.visitedPlaces.filter(place => place.city === destination).map(place => place.name),
    itinerary, stayArea, flights: rankedFlights, returnFlights: rankedReturnFlights, trains: rankedTrains, returnTrains: rankedReturnTrains,
    recommendedOutboundFlightId: preferredFlight?.id || null,
    recommendedOutboundTrainId: preferredTrain?.id || null,
    // 返程最早出发时刻依赖逐日时间轴（真实游玩时长与转场时间），当前没有真实数据来源，
    // 因此不做返程推荐，只保留按价格与红眼排序的返程候选。
    recommendedReturnFlightId: null,
    recommendedReturnTrainId: null,
    returnFlightEarliestAt: null,
    hotels: rankedHotels, providerStatus, providerPriority,
    transportPreference: normalized.transportPreference,
    selectedTransportMode,
    hotelBrands: normalized.hotelBrands,
    generatedAt: new Date().toISOString(),
  };
}
