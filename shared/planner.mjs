import { CITY_CATALOG, DEFAULT_MEMORY } from './catalog.mjs';

const CHINESE_DIGITS = { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7 };
const CATEGORIES = ['海岸', '艺术', '历史街区', '博物馆', '公园', '自然', '城市探索', '街区'];

export function parseTripRequest(text = '') {
  const destination = text.match(/(?:去|到|游玩|游览)([\p{Script=Han}]{2,5}?)(?:玩|旅行|旅游|待|逛|\s|\d|[一二两三四五六七])/u)?.[1] ||
    Object.keys(CITY_CATALOG).find(city => text.includes(city)) || '';
  const match = text.match(/([1-7一二两三四五六七])\s*(?:天|日)/u);
  const days = match ? (Number(match[1]) || CHINESE_DIGITS[match[1]]) : null;
  const interests = CATEGORIES.filter(category => text.includes(category));
  return { destination, days, interests };
}

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

export function estimateTransitMinutes(a, b) {
  const distance = kmBetween(a, b);
  return Math.max(12, Math.round((distance / 22) * 60 + 10));
}

function noveltyScore(place, memory, cityVisited, desiredInterests, destination) {
  if (memory.visitedPlaces.some(item => item.id === place.id || (item.name === place.name && item.city === destination))) return -Infinity;
  const interests = desiredInterests.length ? desiredInterests : memory.interests;
  const farAreaCost = { 龙岗: 2, 罗湖: 1, 盐田: 4, 大鹏: 7 }[place.area] || 0;
  return (interests.includes(place.category) ? 4 : 0) + (cityVisited ? 1 : 0) - farAreaCost;
}

export function selectPlaces(destination, days, memory, desiredInterests = [], livePlaces = []) {
  const cityVisited = memory.visitedCities.includes(destination);
  const catalog = CITY_CATALOG[destination];
  const all = [...(catalog?.places || []), ...livePlaces];
  const unique = [...new Map(all.map(place => [place.id || place.name, place])).values()];
  const candidates = unique
    .map(place => ({ ...place, score: noveltyScore(place, memory, cityVisited, desiredInterests, destination) }))
    .filter(place => Number.isFinite(place.score))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, 'zh'));
  if (!candidates.length) return [];
  const chosen = [];
  const target = Math.min(candidates.length, days === 1 ? 2 : days === 2 ? 4 : 4 + (days - 2) * 3);
  const center = catalog?.center ? { lat: catalog.center[0], lng: catalog.center[1] } : candidates[0];
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

function orderDayPlaces(places) {
  const order = { morning: 0, afternoon: 1, evening: 2 };
  return [...places].sort((a, b) => (order[a.time] ?? 1) - (order[b.time] ?? 1) || a.name.localeCompare(b.name, 'zh'));
}

export function buildDays(places, startDate, days, arrivalIsFlight = true, destination = '', arrivalAt = '', stayArea = null) {
  const catalog = CITY_CATALOG[destination];
  const center = catalog?.center ? { lat: catalog.center[0], lng: catalog.center[1] } : null;
  const airport = arrivalIsFlight ? catalog?.airport : null;
  const arrivalHour = Number(arrivalAt.slice(11, 13));
  const firstStart = arrivalAt && Number.isFinite(arrivalHour) ? Math.max(13 * 60 + 30, arrivalHour * 60 + Number(arrivalAt.slice(14, 16) || 0) + 90) : 13 * 60 + 30;
  const counts = Array.from({ length: days }, (_, index) => days === 1 ? 2 : index === 0 || index === days - 1 ? 2 : 3);
  if (firstStart >= 20 * 60) counts[0] = 0;
  else if (firstStart >= 17 * 60) counts[0] = 1;
  const groups = Array.from({ length: days }, () => []);
  const sequence = days === 1 ? [0] : [0, days - 1, ...Array.from({ length: Math.max(0, days - 2) }, (_, index) => index + 1)];
  let available = [...places];
  for (const [position, index] of sequence.entries()) {
    const anchor = (index === 0 || index === days - 1) ? airport || center : center;
    const balancedCount = Math.min(counts[index], Math.ceil(available.length / (sequence.length - position)));
    const chosen = chooseDayPlaces(available, balancedCount, anchor, index === 0 || index === days - 1, index === days - 1 ? center : null);
    groups[index] = orderDayPlaces(chosen);
    const selectedIds = new Set(chosen.map(place => place.id));
    available = available.filter(place => !selectedIds.has(place.id));
  }
  return groups.map((selected, index) => {
    let minutes = index === 0 ? firstStart : 9 * 60;
    const stops = selected.map((place, placeIndex) => {
      const previous = placeIndex ? selected[placeIndex - 1] : (index === 0 && arrivalIsFlight ? airport : stayArea);
      const travelMinutes = previous ? estimateTransitMinutes(previous, place) : 0;
      minutes += travelMinutes;
      if (place.time === 'afternoon') minutes = Math.max(minutes, 12 * 60 + 30);
      if (place.time === 'evening') minutes = Math.max(minutes, 17 * 60);
      const start = `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
      minutes += place.duration || 90;
      if (placeIndex === 0 && index > 0) minutes += 45;
      return { ...place, start, travelMinutes, travelSource: travelMinutes ? '直线距离估算' : null };
    });
    return { day: index + 1, date: shiftDate(startDate, index), title: selected.length ? `${selected[0].area || destinationArea(selected[0])} · 自由探索` : index === 0 ? '抵达与入住' : '留白 · 自由探索', stops };
  });
}

function destinationArea(place) { return place.category || '城市'; }

export function chooseStayArea(destination, days, memory) {
  const catalog = CITY_CATALOG[destination];
  if (!catalog) return null;
  const points = days.flatMap(day => day.stops);
  if (!points.length) return catalog.neighborhoods[0];
  return catalog.neighborhoods
    .map(area => ({ ...area, averageKm: points.reduce((sum, place) => sum + kmBetween(area, place), 0) / points.length }))
    .sort((a, b) => a.averageKm - b.averageKm)[0];
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

function clockMinutes(value) {
  const hour = Number(value?.slice(11, 13));
  const minute = Number(value?.slice(14, 16));
  return Number.isFinite(hour) && Number.isFinite(minute) ? hour * 60 + minute : null;
}

export function assemblePlan({ destination, originCity, startDate, days, memory, places, flights = [], returnFlights = [], trains = [], returnTrains = [], hotels = [], providerStatus = {}, providerPriority = {}, desiredInterests = [], proposedPlaceIds = [] }) {
  const normalized = normalizeMemory(memory);
  const candidates = selectPlaces(destination, days, normalized, desiredInterests, places);
  const allPlaces = [...(CITY_CATALOG[destination]?.places || []), ...places];
  const selected = proposedPlaceIds.length
    ? proposedPlaceIds.map(id => allPlaces.find(place => place.id === id))
      .filter(place => place && !normalized.visitedPlaces.some(visited => visited.id === place.id || (visited.name === place.name && visited.city === destination)))
    : candidates;
  const rankedFlights = rankFlights(flights, normalized, providerPriority.flights);
  const preferredFlight = rankedFlights.find(flight => !flight.redEye && flight.priceComplete !== false && Number.isFinite(flight.totalPrice));
  const rankedTrains = rankFlights(trains, normalized, providerPriority.trains);
  const preferredTrain = rankedTrains.find(train => !train.redEye && train.priceComplete !== false && Number.isFinite(train.totalPrice));
  const selectedTransportMode = normalized.transportPreference === 'train'
    ? (preferredTrain ? 'train' : preferredFlight ? 'flight' : 'train')
    : (preferredFlight ? 'flight' : preferredTrain ? 'train' : 'flight');
  const arrivalIsFlight = selectedTransportMode === 'flight';
  const selectedArrival = arrivalIsFlight ? preferredFlight?.arrivalAt : preferredTrain?.arrivalAt;
  const initialItinerary = buildDays(selected, startDate, days, arrivalIsFlight, destination, selectedArrival || '');
  const stayArea = chooseStayArea(destination, initialItinerary, normalized);
  const itinerary = buildDays(selected, startDate, days, arrivalIsFlight, destination, selectedArrival || '', stayArea);
  const endDate = shiftDate(startDate, days - 1);
  const finalStop = itinerary.at(-1)?.stops.at(-1);
  const airport = CITY_CATALOG[destination]?.airport;
  const finalActivityEnd = finalStop ? Number(finalStop.start.slice(0, 2)) * 60 + Number(finalStop.start.slice(3, 5)) + finalStop.duration : 9 * 60;
  const returnEarliestMinutes = finalActivityEnd + (airport && finalStop ? estimateTransitMinutes(finalStop, airport) : 90) + 120;
  const rankedReturnFlights = rankFlights(returnFlights, normalized, providerPriority.flights);
  const rankedReturnTrains = rankFlights(returnTrains, normalized, providerPriority.trains);
  const returnTrainEarliestMinutes = finalActivityEnd + 90;
  const recommendedReturnTrain = rankedReturnTrains.find(train => returnTrainEarliestMinutes < 24 * 60 && !train.redEye && train.priceComplete !== false && Number.isFinite(train.totalPrice)
    && train.departureAt.slice(0, 10) === endDate && clockMinutes(train.departureAt) >= returnTrainEarliestMinutes);
  const recommendedReturnFlight = rankedReturnFlights.find(flight => returnEarliestMinutes < 24 * 60 && !flight.redEye && flight.priceComplete !== false && Number.isFinite(flight.totalPrice) && flight.departureAt.slice(0, 10) === endDate
    && clockMinutes(flight.departureAt) >= returnEarliestMinutes);
  const rankedHotels = [...hotels].sort((a, b) => {
    const brand = hotel => normalized.hotelBrands.some(value => hotel.name?.includes(value)) ? -150 : 0;
    const price = hotel => Number(hotel.totalPrice) || 99999;
    const distance = hotel => stayArea && hotel.lat && hotel.lng ? kmBetween(stayArea, hotel) * 15 : 0;
    return price(a) + brand(a) + distance(a) - price(b) - brand(b) - distance(b);
  });
  return {
    destination, originCity, startDate, endDate, days,
    intro: CITY_CATALOG[destination]?.intro || `为你探索${destination}的新地点。`,
    revisit: normalized.visitedCities.includes(destination),
    skippedPlaces: normalized.visitedPlaces.filter(place => place.city === destination).map(place => place.name),
    itinerary, stayArea, flights: rankedFlights, returnFlights: rankedReturnFlights, trains: rankedTrains, returnTrains: rankedReturnTrains,
    recommendedOutboundFlightId: preferredFlight?.id || null,
    recommendedOutboundTrainId: preferredTrain?.id || null,
    recommendedReturnFlightId: recommendedReturnFlight?.id || null,
    recommendedReturnTrainId: recommendedReturnTrain?.id || null,
    returnFlightEarliestAt: returnEarliestMinutes < 24 * 60
      ? `${endDate}T${String(Math.floor(returnEarliestMinutes / 60)).padStart(2, '0')}:${String(returnEarliestMinutes % 60).padStart(2, '0')}` : null,
    hotels: rankedHotels, providerStatus, providerPriority,
    transportPreference: normalized.transportPreference,
    selectedTransportMode,
    hotelBrands: normalized.hotelBrands,
    generatedAt: new Date().toISOString(),
  };
}
