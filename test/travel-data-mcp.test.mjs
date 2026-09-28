import assert from 'node:assert/strict';
import { test } from 'node:test';
import { searchTransport } from '../server/mcp-data/transport.mjs';
import { searchStays } from '../server/mcp-data/stays.mjs';
import { searchAttractions } from '../server/mcp-data/attractions.mjs';
import { searchPlaces } from '../server/mcp-data/places.mjs';
import { createServer } from '../deploy/travel-data-mcp/server.mjs';

test('travel data MCP lists four live tools', async () => {
  const server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const response = await fetch(`http://127.0.0.1:${port}/mcp`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} }) });
    assert.deepEqual((await response.json()).result.tools.map(tool => tool.name), [
      'travel_search_transport', 'travel_search_stays', 'travel_search_attractions', 'travel_search_places']);
  } finally { server.close(); }
});

test('transport MCP preserves full supplier offers and both directions', async () => {
  const offer = { id: 'tuniu-flight-1', departureAt: '2026-10-10T09:00:00', arrivalAt: '2026-10-10T11:00:00',
    totalPrice: 510, currency: 'CNY', airline: '春秋', flightNumber: '9C8956', flightSegments: [{ aircraftModel: null }] };
  const providers = { providerAvailability: () => ({ tuniu: { configured: true, label: '途牛' } }),
    searchTuniuTransport: async kind => kind === 'flight' ? [offer] : [] };
  const data = await searchTransport({ originCity: '深圳', destination: '上海', startDate: '2026-10-10', days: 2 }, {}, providers);
  assert.equal(data.outboundFlights[0].totalPrice, 510);
  assert.equal(data.returnFlights[0].flightSegments.length, 1);
  assert.equal(data.outboundFlights[0].sourceId, 'tuniu');
  assert.equal(data.providerStatus.tuniu.error, false);
});

test('hotel, attraction and place MCP keep normalized source data', async () => {
  const hotels = await searchStays({ city: '深圳', area: '南山', checkInDate: '2026-10-10', stayNights: 1 }, {}, {
    providerAvailability: () => ({ dida: { configured: true } }),
    searchDidaHotels: async () => [{ id: 'h1', totalPrice: 566, lat: 22.5, bookingUrl: 'https://example.com/h1' }],
  });
  assert.equal(hotels.hotels[0].totalPrice, 566);
  const attractions = await searchAttractions({ city: '深圳', places: [{ id: 'p1', name: '世界之窗', visitDate: '2026-10-10' }] }, {}, {
    searchAttractionProducts: async () => [{ provider: '途牛 MCP', sourceId: 'tuniu', name: '世界之窗', price: 180 }],
  });
  assert.equal(attractions.offers[0].price, 180);
  const places = await searchPlaces({ city: '深圳' }, {}, async () => ({ status: 0,
    data: { itemList: [{ id: 'p1', name: '世界之窗', latitude: 22.5, longitude: 113.9 }] } }));
  assert.equal(places.places[0].source, '飞猪 FlyAI');
});
