import test from 'node:test';
import assert from 'node:assert/strict';
import { searchAmapDining, routeMinutes } from '../server/providers.mjs';

test('Amap dining lookup uses nearby food category and keeps only supplied fields', async t => {
  const previousKey = process.env.AMAP_WEB_KEY;
  process.env.AMAP_WEB_KEY = 'test-key';
  t.after(() => { if (previousKey === undefined) delete process.env.AMAP_WEB_KEY; else process.env.AMAP_WEB_KEY = previousKey; });
  let requestUrl;
  t.mock.method(globalThis, 'fetch', async url => {
    requestUrl = new URL(url);
    return { ok: true, json: async () => ({ status: '1', pois: [{
      id: 'B123', name: '海边餐厅', location: '113.900000,22.500000', address: '海边路1号', type: '餐饮服务',
      biz_ext: { rating: '4.4', cost: '88' }, photos: [{ url: 'https://example.com/photo.jpg', title: '门面' }],
    }] }) };
  });
  const items = await searchAmapDining('深圳', [{ day: 2, lat: 22.5, lng: 113.9 }]);
  assert.equal(requestUrl.pathname, '/v3/place/around');
  assert.equal(requestUrl.searchParams.get('types'), '050000');
  assert.equal(requestUrl.searchParams.get('extensions'), 'all');
  assert.equal(items[0].day, 2);
  assert.equal(items[0].averageCost, 88);
  assert.equal(items[0].photos[0].kind, 'poi-photo');
});

test('Amap transit route returns boarding details without claiming street imagery', async t => {
  const previousKey = process.env.AMAP_WEB_KEY;
  process.env.AMAP_WEB_KEY = 'test-key';
  t.after(() => { if (previousKey === undefined) delete process.env.AMAP_WEB_KEY; else process.env.AMAP_WEB_KEY = previousKey; });
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => ({ status: '1', route: { transits: [{
    duration: '2400', walking_distance: '300', cost: '5', segments: [{
      walking: { distance: '300' }, bus: { buslines: [{ name: '地铁11号线', departure_stop: { name: '机场' }, arrival_stop: { name: '前海湾' } }] },
    }],
  }] } }) }));
  const route = await routeMinutes({ lat: 22.64, lng: 113.81 }, { lat: 22.54, lng: 113.99 }, '深圳');
  assert.equal(route.minutes, 40);
  assert.equal(route.walkingMeters, 300);
  assert.equal(route.segments[1].board, '机场');
  assert.equal(route.fare, 5);
  assert.equal(route.imagery, undefined);
});
