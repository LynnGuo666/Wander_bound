import test from 'node:test';
import assert from 'node:assert/strict';
import { assemblePlan, chooseStayArea, normalizeMemory, rankFlights, selectPlaces } from '../shared/planner.mjs';

// 测试夹具模拟高德 POI 的真实形状：没有游玩时长（duration: null），没有时刻。
const livePlaces = [
  { id: 'p-nantou', name: '南头古城', lat: 22.5345, lng: 113.9233, area: '南山', category: '历史街区', duration: null },
  { id: 'p-oct', name: '华侨城创意文化园', lat: 22.5428, lng: 113.9864, area: '南山', category: '艺术', duration: null },
  { id: 'p-bay', name: '深圳湾公园', lat: 22.5160, lng: 113.9440, area: '南山', category: '海岸', duration: null },
  { id: 'p-seaworld', name: '海上世界', lat: 22.4848, lng: 113.9182, area: '蛇口', category: '街区', duration: null },
  { id: 'p-museum', name: '深圳博物馆', lat: 22.5458, lng: 114.0606, area: '福田', category: '博物馆', duration: null },
  { id: 'p-lianhuashan', name: '莲花山公园', lat: 22.5560, lng: 114.0614, area: '福田', category: '公园', duration: null },
  { id: 'p-huaqiangbei', name: '华强北', lat: 22.5457, lng: 114.0885, area: '福田', category: '城市探索', duration: null },
  { id: 'p-baoanbay', name: '欢乐港湾', lat: 22.5527, lng: 113.8794, area: '宝安', category: '海岸', duration: null },
  { id: 'p-dafen', name: '大芬油画村', lat: 22.6142, lng: 114.1362, area: '龙岗', category: '艺术', duration: null },
  { id: 'p-gankeng', name: '甘坑古镇', lat: 22.6302, lng: 114.0906, area: '龙岗', category: '历史街区', duration: null },
];

const base = { destination: '深圳', originCity: '上海', startDate: '2026-10-09', days: 3, places: livePlaces };

test('a return visit skips visited places and keeps every day unique and unscheduled', () => {
  const memory = normalizeMemory({
    visitedCities: ['深圳'],
    visitedPlaces: [
      { id: 'p-oct', name: '华侨城创意文化园', city: '深圳' },
      { id: 'p-bay', name: '深圳湾公园', city: '深圳' },
    ],
  });
  const plan = assemblePlan({ ...base, memory });
  const names = plan.itinerary.flatMap(day => day.stops.map(stop => stop.name));
  assert.equal(plan.revisit, true);
  assert.equal(plan.itinerary.length, 3);
  assert.deepEqual(plan.itinerary.map(day => day.stops.length), [2, 3, 2]);
  assert.equal(new Set(names).size, names.length);
  assert.ok(!names.includes('华侨城创意文化园'));
  assert.ok(!names.includes('深圳湾公园'));
  const stops = plan.itinerary.flatMap(day => day.stops);
  assert.ok(stops.every(stop => stop.start === null));
  assert.ok(stops.every(stop => stop.travelMinutes === null && stop.travelSource === null));
});

test('a late arrival leaves the first evening free of impossible activities', () => {
  const plan = assemblePlan({
    ...base,
    memory: normalizeMemory(),
    flights: [{ id: 'late', departureAt: '2026-10-09T17:00:00', arrivalAt: '2026-10-09T22:10:00', totalPrice: 450, stops: 0 }],
  });
  assert.equal(plan.itinerary[0].stops.length, 0);
  assert.equal(plan.itinerary[0].title, '抵达与入住');
});

test('prefers an affordable daytime flight over a cheaper red-eye flight', () => {
  const ranked = rankFlights([
    { id: 'night', departureAt: '2026-10-09T23:00:00', arrivalAt: '2026-10-10T01:00:00', totalPrice: 320, stops: 0 },
    { id: 'day', departureAt: '2026-10-09T10:00:00', arrivalAt: '2026-10-09T12:30:00', totalPrice: 470, stops: 0 },
  ], normalizeMemory());
  assert.deepEqual(ranked.map(flight => flight.id), ['day', 'night']);
  assert.equal(ranked[1].redEye, true);
});

test('outbound train recommendation follows source priority and falls back when its first source has no price', () => {
  const memory = normalizeMemory({ transportPreference: 'train' });
  const offers = [
    { id: 'rail', sourceId: 'rail12306', departureAt: '2026-10-09T08:00:00', arrivalAt: '2026-10-09T15:00:00', totalPrice: 800, stops: 0 },
    { id: 'flyai', sourceId: 'flyai', departureAt: '2026-10-09T09:00:00', arrivalAt: '2026-10-09T16:00:00', totalPrice: 500, stops: 0 },
  ];
  const preferences = { trains: ['rail12306', 'flyai', 'tuniu'] };
  const preferred = assemblePlan({ ...base, memory, trains: offers, providerPriority: preferences });
  assert.equal(preferred.recommendedOutboundTrainId, 'rail');
  const fallback = assemblePlan({ ...base, memory, trains: [{ ...offers[0], totalPrice: null }, offers[1]], providerPriority: preferences });
  assert.equal(fallback.recommendedOutboundTrainId, 'flyai');
  assert.equal(fallback.trains.length, 2);
});

test('return recommendations stay empty without a verified day timeline', () => {
  const plan = assemblePlan({ ...base, memory: normalizeMemory(), returnFlights: [
    { id: 'feasible', departureAt: '2026-10-11T18:30:00', arrivalAt: '2026-10-11T21:00:00', totalPrice: 500, stops: 0 },
  ] });
  assert.equal(plan.recommendedReturnFlightId, null);
  assert.equal(plan.recommendedReturnTrainId, null);
  assert.equal(plan.returnFlightEarliestAt, null);
  assert.equal(plan.returnFlights.length, 1);
});

test('without supplier keys, quotes and reviews remain absent', () => {
  const plan = assemblePlan({ ...base, memory: normalizeMemory() });
  assert.deepEqual(plan.flights, []);
  assert.deepEqual(plan.hotels, []);
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => stop.rating === undefined));
});

test('stay area is derived from the selected places, not from a hand-edited list', () => {
  const plan = assemblePlan({ ...base, memory: normalizeMemory() });
  assert.ok(plan.stayArea);
  const counts = new Map();
  for (const stop of plan.itinerary.flatMap(day => day.stops)) counts.set(stop.area, (counts.get(stop.area) || 0) + 1);
  const dominant = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
  assert.equal(plan.stayArea.name, dominant);
  assert.ok(Number.isFinite(plan.stayArea.lat) && Number.isFinite(plan.stayArea.lng));
  assert.equal(chooseStayArea([{ day: 1, stops: [] }]), null);
});

test('a same-named place in another city does not block a visit', () => {
  const memory = normalizeMemory({ visitedPlaces: [{ id: 'other-city-place', name: '南头古城', city: '北京' }] });
  assert.ok(selectPlaces('深圳', 3, memory, [], livePlaces).some(place => place.id === 'p-nantou'));
});

test('no places means no fabricated itinerary content', () => {
  const plan = assemblePlan({ ...base, places: [], memory: normalizeMemory() });
  assert.equal(plan.itinerary.length, 3);
  assert.ok(plan.itinerary.every(day => day.stops.length === 0));
  assert.equal(plan.stayArea, null);
});
