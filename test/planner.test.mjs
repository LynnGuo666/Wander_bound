import test from 'node:test';
import assert from 'node:assert/strict';
import { assemblePlan, normalizeMemory, parseTripRequest, rankFlights, selectPlaces } from '../shared/planner.mjs';

const base = { destination: '深圳', originCity: '上海', startDate: '2026-10-09', days: 3, places: [] };

test('understands a three-day Shenzhen request', () => {
  assert.deepEqual(parseTripRequest('我想去深圳玩三天，喜欢海岸'), { destination: '深圳', days: 3, interests: ['海岸'] });
  assert.equal(parseTripRequest('从深圳去上海玩三天').destination, '上海');
});

test('a return visit skips known places and keeps the return day light', () => {
  const memory = normalizeMemory({
    visitedCities: ['深圳'],
    visitedPlaces: [
      { id: 'sz-oct', name: '华侨城创意文化园', city: '深圳' },
      { id: 'sz-bay', name: '深圳湾公园', city: '深圳' },
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
  assert.ok(plan.itinerary[2].stops.every(stop => !['大鹏', '盐田', '龙岗'].includes(stop.area)));
  assert.ok(plan.itinerary.flatMap(day => day.stops).some(stop => stop.travelSource === '直线距离估算'));
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => stop.time !== 'evening' || stop.start >= '17:00'));
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => stop.time !== 'afternoon' || stop.start >= '12:30'));
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

test('return flight recommendation leaves time for the last activity and airport transfer', () => {
  const plan = assemblePlan({ ...base, memory: normalizeMemory(), returnFlights: [
    { id: 'too-early', departureAt: '2026-10-11T15:00:00', arrivalAt: '2026-10-11T17:30:00', totalPrice: 350, stops: 0 },
    { id: 'feasible', departureAt: '2026-10-11T18:30:00', arrivalAt: '2026-10-11T21:00:00', totalPrice: 500, stops: 0 },
    { id: 'overnight', departureAt: '2026-10-11T23:00:00', arrivalAt: '2026-10-12T01:30:00', totalPrice: 250, stops: 0 },
  ] });
  assert.equal(plan.recommendedReturnFlightId, 'feasible');
  assert.equal(plan.returnFlights.length, 3);
  assert.ok(plan.returnFlightEarliestAt < '2026-10-11T18:30');
});

test('without supplier keys, quotes and reviews remain absent', () => {
  const plan = assemblePlan({ ...base, memory: normalizeMemory() });
  assert.deepEqual(plan.flights, []);
  assert.deepEqual(plan.hotels, []);
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => stop.rating === undefined));
});

test('a same-named place in another city does not block a Shenzhen visit', () => {
  const memory = normalizeMemory({ visitedPlaces: [{ id: 'other-city-place', name: '南头古城', city: '北京' }] });
  assert.ok(selectPlaces('深圳', 3, memory).some(place => place.id === 'sz-nantou'));
});
