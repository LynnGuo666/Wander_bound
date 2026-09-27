import { CITY_AIRPORTS, CITY_CATALOG } from '../shared/catalog.mjs';
import { kmBetween } from '../shared/planner.mjs';
import { searchFlyai, searchFlyaiAttractions, searchTuniu, searchTuniuTickets } from './ota-cli.mjs';

const controllerFor = (milliseconds = 9000) => AbortSignal.timeout(milliseconds);

async function jsonGet(url, timeout = 9000) {
  const response = await fetch(url, { signal: controllerFor(timeout) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function reverseLocation(location) {
  if (!process.env.AMAP_WEB_KEY || !location?.lat || !location?.lng) return null;
  const url = new URL('https://restapi.amap.com/v3/geocode/regeo');
  url.searchParams.set('key', process.env.AMAP_WEB_KEY);
  url.searchParams.set('location', `${location.lng.toFixed(6)},${location.lat.toFixed(6)}`);
  const payload = await jsonGet(url);
  if (payload.status !== '1') throw new Error(payload.info || '高德逆地理编码失败');
  const city = payload.regeocode?.addressComponent?.city;
  const province = payload.regeocode?.addressComponent?.province;
  return Array.isArray(city) ? province?.replace(/[市省]$/, '') : city?.replace(/市$/, '');
}

function categoryFor(name, type) {
  if (/海|湾|滨/.test(name)) return '海岸';
  if (/博物馆|纪念馆/.test(name)) return '博物馆';
  if (/美术|艺术|画/.test(name)) return '艺术';
  if (/古镇|古城|老街/.test(name)) return '历史街区';
  if (/植物|山|森林/.test(name)) return '自然';
  if (/公园/.test(name)) return '公园';
  if (/景点|景区/.test(type)) return '城市探索';
  return '街区';
}

export async function searchAmapPlaces(city) {
  if (!process.env.AMAP_WEB_KEY) return [];
  const keywords = ['景点', '博物馆', '公园'];
  const responses = await Promise.allSettled(keywords.map(async keyword => {
    const url = new URL('https://restapi.amap.com/v3/place/text');
    url.searchParams.set('key', process.env.AMAP_WEB_KEY);
    url.searchParams.set('keywords', keyword);
    url.searchParams.set('city', city);
    url.searchParams.set('citylimit', 'true');
    url.searchParams.set('offset', '15');
    url.searchParams.set('extensions', 'all');
    const payload = await jsonGet(url);
    if (payload.status !== '1') throw new Error(payload.info || '高德地点搜索失败');
    return payload.pois || [];
  }));
  const found = responses.flatMap(item => item.status === 'fulfilled' ? item.value : []);
  return [...new Map(found.map(poi => [poi.id, poi])).values()]
    .map(poi => {
      const [lng, lat] = String(poi.location || '').split(',').map(Number);
      return {
        id: `amap-${poi.id}`, name: poi.name, lat, lng, area: String(poi.adname || poi.business_area || '城市').replace(/区$/, ''),
        category: categoryFor(poi.name, poi.type), duration: 100, description: poi.address || '留出时间自由探索周边。',
        rating: Number(poi.biz_ext?.rating) || null, ratingSource: poi.biz_ext?.rating ? '高德' : null,
        source: '高德地点搜索',
      };
    })
    .filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lng));
}

export async function searchAmapDining(city, anchors = []) {
  if (!process.env.AMAP_WEB_KEY) return [];
  const points = anchors.filter(point => Number.isFinite(point?.lat) && Number.isFinite(point?.lng)).slice(0, 7);
  const responses = await Promise.allSettled(points.map(async (point, day) => {
    const url = new URL('https://restapi.amap.com/v3/place/around');
    url.searchParams.set('key', process.env.AMAP_WEB_KEY);
    url.searchParams.set('location', `${point.lng.toFixed(6)},${point.lat.toFixed(6)}`);
    url.searchParams.set('city', city);
    url.searchParams.set('types', '050000');
    url.searchParams.set('radius', '1800');
    url.searchParams.set('sortrule', 'weight');
    url.searchParams.set('offset', '15');
    url.searchParams.set('extensions', 'all');
    const payload = await jsonGet(url, 7000);
    if (payload.status !== '1') throw new Error(payload.info || '高德餐饮搜索失败');
    return (payload.pois || []).map(poi => ({ poi, day: point.day || day + 1 }));
  }));
  if (responses.length && responses.every(item => item.status === 'rejected')) throw responses[0].reason;
  return responses.flatMap(item => item.status === 'fulfilled' ? item.value : [])
    .map(({ poi, day }) => {
      const [lng, lat] = String(poi.location || '').split(',').map(Number);
      const rating = Number(poi.biz_ext?.rating);
      const averageCost = Number(poi.biz_ext?.cost);
      return {
        id: `amap-${poi.id}`, providerPlaceId: String(poi.id || ''), name: String(poi.name || ''), day, lat, lng,
        address: String(poi.address || ''), type: String(poi.type || ''),
        rating: Number.isFinite(rating) && rating > 0 ? rating : null,
        averageCost: Number.isFinite(averageCost) && averageCost > 0 ? averageCost : null,
        currency: 'CNY', photos: (Array.isArray(poi.photos) ? poi.photos : [])
          .filter(photo => /^https:\/\//.test(photo.url || '')).slice(0, 2)
          .map(photo => ({ url: photo.url, caption: String(photo.title || photo.titile || ''), kind: 'poi-photo' })),
        source: '高德餐饮 POI',
        sourceRecords: [{ provider: '高德', placeId: String(poi.id || ''),
          rating: Number.isFinite(rating) && rating > 0 ? rating : null,
          averageCost: Number.isFinite(averageCost) && averageCost > 0 ? averageCost : null,
          currency: 'CNY', kind: 'place-data' }],
      };
    })
    .filter(poi => poi.id !== 'amap-undefined' && poi.name && Number.isFinite(poi.lat) && Number.isFinite(poi.lng));
}

export async function routeMinutes(origin, destination, city) {
  if (!process.env.AMAP_WEB_KEY || !origin || !destination) return null;
  const walking = kmBetween(origin, destination) < 1.8;
  const url = new URL(`https://restapi.amap.com/v3/direction/${walking ? 'walking' : 'transit/integrated'}`);
  url.searchParams.set('key', process.env.AMAP_WEB_KEY);
  url.searchParams.set('origin', `${origin.lng},${origin.lat}`);
  url.searchParams.set('destination', `${destination.lng},${destination.lat}`);
  if (!walking) url.searchParams.set('city', city);
  const payload = await jsonGet(url, 7000);
  if (payload.status !== '1') throw new Error(payload.info || '路线查询失败');
  const seconds = Number(walking ? payload.route?.paths?.[0]?.duration : payload.route?.transits?.[0]?.duration);
  if (!(seconds > 0)) return null;
  const path = walking ? payload.route?.paths?.[0] : payload.route?.transits?.[0];
  const segments = walking
    ? (path?.steps || []).slice(0, 8).map(step => ({ mode: 'walk', instruction: String(step.instruction || '').slice(0, 160), distanceMeters: Number(step.distance) || null }))
    : (path?.segments || []).slice(0, 8).flatMap(segment => {
      const items = [];
      if (Number(segment.walking?.distance) > 0) items.push({ mode: 'walk', distanceMeters: Number(segment.walking.distance) });
      const line = segment.bus?.buslines?.[0];
      if (line) items.push({ mode: 'transit', line: String(line.name || '').slice(0, 100), board: String(line.departure_stop?.name || ''), alight: String(line.arrival_stop?.name || '') });
      return items;
    });
  return {
    minutes: Math.ceil(seconds / 60), source: walking ? '高德步行路线' : '高德公共交通', mode: walking ? 'walk' : 'transit',
    walkingMeters: walking ? Number(path?.distance) || null : Number(path?.walking_distance) || null,
    fare: walking ? null : Number(path?.cost) || null,
    currency: walking ? null : 'CNY', segments,
  };
}

export async function enrichRoutes(plan) {
  if (!process.env.AMAP_WEB_KEY) return plan;
  const airport = CITY_CATALOG[plan.destination]?.airport;
  const groundJourneys = [];
  const itineraries = await Promise.all(plan.itinerary.map(async (day, index) => {
    const stops = await Promise.all(day.stops.map(async (stop, stopIndex) => {
      const origin = stopIndex ? day.stops[stopIndex - 1] : (index === 0 && plan.selectedTransportMode === 'flight' ? airport : plan.stayArea);
      if (!origin) return stop;
      try {
        const route = await routeMinutes(origin, stop, plan.destination);
        if (route) groundJourneys.push({ day: day.day, stopIndex, from: origin.name || (index === 0 && plan.selectedTransportMode === 'flight' ? '机场' : '住宿区域'), to: stop.name,
          fromCoordinate: { lat: origin.lat, lng: origin.lng }, toCoordinate: { lat: stop.lat, lng: stop.lng },
          ...route, imagery: { status: 'check-on-device', provider: 'Apple MapKit Look Around' } });
        return route ? { ...stop, travelMinutes: route.minutes, travelSource: route.source } : stop;
      } catch { return stop; }
    }));
    let shift = 0;
    return { ...day, stops: stops.map((stop, stopIndex) => {
      const original = day.stops[stopIndex];
      shift += stop.travelMinutes - original.travelMinutes;
      const originalMinutes = Number(original.start.slice(0, 2)) * 60 + Number(original.start.slice(3, 5));
      const floor = stop.time === 'evening' ? 17 * 60 : stop.time === 'afternoon' ? 12 * 60 + 30 : 0;
      const nextMinutes = Math.max(floor, originalMinutes + shift);
      shift = nextMinutes - originalMinutes;
      return { ...stop, start: `${String(Math.floor(nextMinutes / 60)).padStart(2, '0')}:${String(nextMinutes % 60).padStart(2, '0')}` };
    }) };
  }));
  return { ...plan, itinerary: itineraries, groundJourneys: groundJourneys.sort((a, b) => a.day - b.day || a.stopIndex - b.stopIndex)
    .map(({ stopIndex, ...journey }) => journey) };
}

function unpackMcp(body) {
  const records = body.trim().startsWith('data:')
    ? body.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).filter(line => line !== '[DONE]')
    : [body];
  for (const record of records.reverse()) {
    try {
      const parsed = JSON.parse(record);
      if (parsed.result?.content) {
        const text = parsed.result.content.find(item => item.type === 'text')?.text;
        try { return JSON.parse(text); } catch { return { raw: text }; }
      }
      return parsed.result || parsed;
    } catch { /* Continue until a valid JSON data record is found. */ }
  }
  throw new Error('酒店服务没有返回可解析的数据');
}

export async function searchDidaHotels(city, area, startDate, stayNights, budget) {
  if (!process.env.DIDA_API_KEY) return [];
  const response = await fetch('https://mcp.rollinggo.cn/mcp', {
    method: 'POST',
    signal: controllerFor(14000),
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${process.env.DIDA_API_KEY}`,
    },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 1, method: 'tools/call',
      params: {
        name: 'searchHotels',
        arguments: {
          originQuery: `${city}${area || ''}附近酒店，每晚不高于${budget}元`,
          place: `${city}${area || ''}`, placeType: area ? '区/县' : '城市',
          checkInParam: { checkInDate: startDate, stayNights },
          size: 12,
        },
      },
    }),
  });
  if (!response.ok) throw new Error(`道旅 HTTP ${response.status}`);
  const payload = unpackMcp(await response.text());
  const items = Array.isArray(payload) ? payload : payload.hotels || payload.data?.hotels || payload.data?.list || payload.list || [];
  return items.map((hotel, index) => {
    const location = hotel.location || hotel.coordinates || {};
    const rawPrice = hotel.totalPrice || hotel.price?.total || hotel.price || hotel.minPrice || hotel.displayPrice;
    const amount = typeof rawPrice === 'object' ? rawPrice.amount || rawPrice.value : rawPrice;
    return {
      id: String(hotel.hotelId || hotel.id || `dida-${index}`), provider: '道旅', name: hotel.hotelName || hotel.name || '未命名酒店',
      address: hotel.address || hotel.hotelAddress || '',
      lat: Number(hotel.latitude || location.lat) || null, lng: Number(hotel.longitude || location.lng) || null,
      displayPrice: Number(amount) || null,
      priceBasis: hotel.totalPrice ? '总价' : '展示价，预订前验价',
      totalPrice: Number(hotel.totalPrice) || null,
      currency: hotel.currency || 'CNY',
      rating: Number(hotel.rating || hotel.score) || null,
      bookingUrl: hotel.bookingUrl || hotel.bookUrl || hotel.url || null,
    };
  });
}

export async function searchDuffelFlights(originCity, destinationCity, date) {
  if (!process.env.DUFFEL_API_KEY || !CITY_AIRPORTS[originCity] || !CITY_AIRPORTS[destinationCity] || originCity === destinationCity) return [];
  const response = await fetch('https://api.duffel.com/air/offer_requests', {
    method: 'POST', signal: controllerFor(15000),
    headers: {
      Authorization: `Bearer ${process.env.DUFFEL_API_KEY}`,
      'Duffel-Version': 'v2', 'Content-Type': 'application/json', Accept: 'application/json',
    },
    body: JSON.stringify({ data: {
      slices: [{ origin: CITY_AIRPORTS[originCity], destination: CITY_AIRPORTS[destinationCity], departure_date: date }],
      passengers: [{ type: 'adult' }], cabin_class: 'economy', max_connections: 1,
    } }),
  });
  if (!response.ok) throw new Error(`Duffel HTTP ${response.status}`);
  const payload = await response.json();
  return (payload.data?.offers || []).slice(0, 30).map(offer => {
    const segments = offer.slices?.[0]?.segments || [];
    return {
      id: offer.id, provider: 'Duffel', airline: segments[0]?.operating_carrier?.name || segments[0]?.marketing_carrier?.name || '航空公司',
      flightNumber: segments.map(segment => `${segment.marketing_carrier?.iata_code || ''}${segment.marketing_carrier_flight_number || ''}`).join(' · '),
      departureAt: segments[0]?.departing_at || '', arrivalAt: segments.at(-1)?.arriving_at || '',
      origin: segments[0]?.origin?.iata_code || CITY_AIRPORTS[originCity],
      destination: segments.at(-1)?.destination?.iata_code || CITY_AIRPORTS[destinationCity],
      stops: Math.max(0, segments.length - 1), totalPrice: Number(offer.total_amount), currency: offer.total_currency,
      priceComplete: true, priceBasis: '供应商总价',
      expiresAt: offer.expires_at,
    };
  }).filter(flight => Number.isFinite(flight.totalPrice));
}

export function providerAvailability() {
  return {
    amap: { configured: Boolean(process.env.AMAP_WEB_KEY), label: '高德地点与路线' },
    dida: { configured: Boolean(process.env.DIDA_API_KEY), label: '道旅酒店' },
    duffel: { configured: Boolean(process.env.DUFFEL_API_KEY), label: 'Duffel 航班' },
    tuniu: { configured: Boolean(process.env.TUNIU_API_KEY || process.env.TUNIU_USE_OAUTH === '1'), installed: true, label: '途牛 MCP CLI' },
    flyai: { configured: true, installed: true, mode: process.env.FLYAI_API_KEY ? 'key' : 'trial', label: '飞猪 FlyAI Skill/CLI' },
    trip: { configured: false, label: '携程景区合作方接口' },
    reviews: { configured: false, label: '大众点评/美团评论 MCP' },
  };
}

export async function searchFlyaiTransport(kind, origin, destination, date) {
  if (!origin || !destination) return [];
  return searchFlyai(kind, origin, destination, date);
}

export async function searchTuniuTransport(kind, origin, destination, date) {
  if (!providerAvailability().tuniu.configured || !origin || !destination) return [];
  return searchTuniu(kind, origin, destination, date);
}

export async function searchAttractionProducts(city, places) {
  const targets = places.filter(place => !/公园|广场|街区|海滩|海湾/.test(place.name)).slice(0, 7);
  const jobs = targets.flatMap(place => [
    { place, promise: searchFlyaiAttractions(city, place.name) },
    ...(providerAvailability().tuniu.configured ? [{ place, promise: searchTuniuTickets(place.name, place.visitDate) }] : []),
  ]);
  const responses = await Promise.allSettled(jobs.map(job => job.promise));
  if (jobs.length && responses.every(item => item.status === 'rejected')) throw responses[0].reason;
  const canonical = name => {
    const value = String(name || '').trim();
    return (value.startsWith(city) ? value.slice(city.length) : value).replace(/(?:风景区|景区)$/, '').trim();
  };
  const matched = responses.flatMap((item, index) => item.status === 'fulfilled'
    ? item.value.filter(offer => canonical(offer.name) === canonical(jobs[index].place.name))
      .map(offer => ({ ...offer, placeId: jobs[index].place.id })) : []);
  return [...new Map(matched.map(offer => [`${offer.placeId}:${offer.provider}:${offer.productName}:${offer.price}`, offer])).values()];
}
