import { kmBetween } from '../../shared/planner.mjs';
import { jsonGet } from './http-client.mjs';

export async function reverseLocation(location, key = process.env.AMAP_WEB_KEY) {
  if (!key || !location?.lat || !location?.lng) return null;
  const url = new URL('https://restapi.amap.com/v3/geocode/regeo');
  url.searchParams.set('key', key);
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

export async function searchAmapPlaces(city, key = process.env.AMAP_WEB_KEY) {
  if (!key) return [];
  const keywords = ['景点', '博物馆', '公园'];
  const responses = await Promise.allSettled(keywords.map(async keyword => {
    const url = new URL('https://restapi.amap.com/v3/place/text');
    url.searchParams.set('key', key);
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
        // 高德不提供游玩时长；留空并交由能力状态标注“时长未核实”，不编造数值。
        category: categoryFor(poi.name, poi.type), duration: null, description: poi.address || '留出时间自由探索周边。',
        rating: Number(poi.biz_ext?.rating) || null, ratingSource: poi.biz_ext?.rating ? '高德' : null,
        source: '高德地点搜索',
      };
    })
    .filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lng));
}

export async function searchAmapDining(city, anchors = [], key = process.env.AMAP_WEB_KEY) {
  if (!key) return [];
  const points = anchors.filter(point => Number.isFinite(point?.lat) && Number.isFinite(point?.lng)).slice(0, 7);
  const responses = await Promise.allSettled(points.map(async (point, day) => {
    const url = new URL('https://restapi.amap.com/v3/place/around');
    url.searchParams.set('key', key);
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

export async function routeMinutes(origin, destination, city, key = process.env.AMAP_WEB_KEY) {
  if (!key || !origin || !destination) return null;
  const walking = kmBetween(origin, destination) < 1.8;
  const url = new URL(`https://restapi.amap.com/v3/direction/${walking ? 'walking' : 'transit/integrated'}`);
  url.searchParams.set('key', key);
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

export async function enrichRoutes(plan, key = process.env.AMAP_WEB_KEY) {
  if (!key) return plan;
  const groundJourneys = [];
  const itineraries = await Promise.all(plan.itinerary.map(async (day, index) => {
    const stops = await Promise.all(day.stops.map(async (stop, stopIndex) => {
      // 第一天第一段没有真实的抵达点（机场/车站坐标无数据来源），跳过而不估算。
      const origin = stopIndex ? day.stops[stopIndex - 1] : (index === 0 ? null : plan.stayArea);
      if (!origin || !Number.isFinite(origin.lat) || !Number.isFinite(origin.lng)) return stop;
      try {
        const route = await routeMinutes(origin, stop, plan.destination, key);
        if (route) groundJourneys.push({ day: day.day, stopIndex, from: origin.name, to: stop.name,
          fromCoordinate: { lat: origin.lat, lng: origin.lng }, toCoordinate: { lat: stop.lat, lng: stop.lng },
          ...route, imagery: { status: 'check-on-device', provider: 'Apple MapKit Look Around' } });
        return route ? { ...stop, travelMinutes: route.minutes, travelSource: route.source } : stop;
      } catch { return stop; }
    }));
    return { ...day, stops };
  }));
  return { ...plan, itinerary: itineraries, groundJourneys: groundJourneys.sort((a, b) => a.day - b.day || a.stopIndex - b.stopIndex)
    .map(({ stopIndex, ...journey }) => journey) };
}
