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

test('Dida hotels use the real searchHotels schema captured on 2026-09-28', async t => {
  const { normalizeDidaHotels } = await import('../server/providers/dida.mjs');
  const realRecord = {
    hotelId: 2307050,
    bookingUrl: 'https://rollinggo.cn/pages/hotel/detail/index?id=2307050&checkInDate=2026-10-15&checkOutDate=2026-10-16',
    name: '深圳南山万象青华酒店(万象天地店)',
    address: '科技园高新南六道10号朗科大厦1楼',
    latitude: 22.535646, longitude: 113.953154,
    starRating: 4.0,
    price: { message: '查价成功。1晚总价：566CNY（约566CNY/晚）', hasPrice: true, currency: 'CNY', lowestPrice: 566.0 },
    imageUrl: 'https://image-cdn.rollinggo.cn/v2/2307050/hotel/default/14/image/1mc6u12000q7eh9zx194A_R_960_660_R5_D.jpg-t',
  };
  const [priced] = normalizeDidaHotels([realRecord, { hotelId: 2, name: '无价酒店', price: { hasPrice: false, message: '暂无报价' } }], 1);
  assert.equal(priced.id, '2307050');
  assert.equal(priced.provider, '道旅');
  assert.equal(priced.totalPrice, 566);
  assert.equal(priced.displayPrice, 566);
  assert.equal(priced.currency, 'CNY');
  assert.equal(priced.rating, 4);
  assert.equal(priced.priceBasis, '查询时1晚总价，预订前验价');
  assert.equal(priced.lat, 22.535646);
  assert.ok(priced.bookingUrl.startsWith('https://'));
  const [, unpriced] = normalizeDidaHotels([realRecord, { hotelId: 2, name: '无价酒店', price: { hasPrice: false, message: '暂无报价' } }]);
  assert.equal(unpriced.totalPrice, null);
  assert.equal(unpriced.displayPrice, null);
  assert.equal(unpriced.priceBasis, '未取得价格');
});
