import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeFlyaiAttractions, normalizeFlyaiTransport, normalizeTuniuFlights, normalizeTuniuTrains, searchFlyai, searchFlyaiAttractions, searchTuniu, searchTuniuTickets, unwrapTuniu } from '../server/ota-cli.mjs';

test('official CLI commands use documented read-only tool names and arguments', async () => {
  const calls = [];
  const runner = async (binary, args) => {
    calls.push({ binary, args });
    return binary === 'flyai' ? { status: 0, data: { itemList: [] } } : { success: true, result: { successCode: true, data: [] } };
  };
  await searchFlyai('flight', '上海', '深圳', '2026-10-09', runner);
  await searchFlyai('train', '上海', '深圳', '2026-10-09', runner);
  await searchFlyaiAttractions('深圳', '仙湖植物园', runner);
  await searchTuniu('flight', '上海', '深圳', '2026-10-09', runner);
  await searchTuniu('train', '上海', '深圳', '2026-10-09', runner);
  await searchTuniuTickets('世界之窗', '2026-10-09', runner);
  assert.deepEqual(calls[0], { binary: 'flyai', args: ['search-flight', '--origin', '上海', '--destination', '深圳', '--dep-date', '2026-10-09', '--sort-type', '3'] });
  assert.equal(calls[1].args[0], 'search-train');
  assert.deepEqual(calls[2].args, ['search-poi', '--city-name', '深圳', '--keyword', '仙湖植物园']);
  assert.deepEqual(calls[3].args.slice(0, 4), ['call', 'flight', 'searchLowestPriceFlight', '-a']);
  assert.deepEqual(JSON.parse(calls[3].args[4]), { departureCityName: '上海', arrivalCityName: '深圳', departureDate: '2026-10-09' });
  assert.equal(calls[4].args[2], 'searchLowestPriceTrain');
  assert.deepEqual(JSON.parse(calls[5].args[4]), { scenic_name: '世界之窗', depart_date: '2026-10-09' });
});

test('MCP envelope is decoded; redacted trial prices remain unknown schedules', () => {
  assert.deepEqual(unwrapTuniu({ success: true, result: { content: [{ type: 'text', text: '{"successCode":true,"data":[]}' }] } }), { successCode: true, data: [] });
  const rows = [{ adultPrice: '¥2xx', journeys: [{ segments: [{ depDateTime: '2026-10-09 09:00:00', arrDateTime: '2026-10-09 11:00:00' }] }] }];
  assert.equal(normalizeFlyaiTransport(rows, 'flight')[0].totalPrice, null);
  assert.equal(normalizeFlyaiAttractions([{ id: '72', name: '深圳世界之窗', ticketInfo: { price: '¥2xx' } }])[0].price, null);
});

test('real Tuniu CLI triple-nested envelope unwraps to business data (captured 2026-09-28)', () => {
  const business = { successCode: true, queryId: 'q-1', totalPageNum: 1, data: [{
    airlineCompany: '春秋', flightNumber: '9C8956', craftType: 'A321',
    departureTime: '2026-10-15 07:15', arrivalTime: '2026-10-15 09:35',
    departureAirport: '宝安', arrivalAirport: '虹桥', departureTerminal: 'T3', arrivalTerminal: 'T1',
    cabinClass: '经济舱', remainingSeats: '9', type: '直飞', basePrice: '390', totalTax: '120',
  }] };
  // 途牛 CLI 的 structuredContent.result 与 content 文本承载同一业务 JSON；两种载体都必须解出。
  const envelope = object => ({ success: true, result: { content: [{ type: 'text', text: JSON.stringify(object) }], structuredContent: { result: object }, isError: false } });
  const asObject = unwrapTuniu(envelope(business));
  assert.deepEqual(asObject, business);
  const [flight] = normalizeTuniuFlights(asObject, '2026-10-15');
  assert.equal(flight.flightNumber, '9C8956');
  assert.equal(flight.departureAt, '2026-10-15T07:15:00');
  assert.equal(flight.totalPrice, 510);
  assert.equal(flight.basePrice, 390);
  assert.equal(flight.taxAmount, 120);
  assert.equal(flight.priceComplete, true);
  const asString = unwrapTuniu({ success: true, result: { structuredContent: { result: JSON.stringify(business) } } });
  assert.deepEqual(asString, business);
});

test('complete FlyAI flight and train results preserve source, date, price and deep link', () => {
  const item = { id: 'quote-1', ticketPrice: '400.00', jumpUrl: 'https://example.com/book', journeys: [{ segments: [{ depDateTime: '2026-10-09 08:00:00', arrDateTime: '2026-10-09 10:00:00', depStationName: '虹桥', arrStationName: '深圳北', marketingTransportNo: 'G1', seatClassName: '二等座' }] }] };
  const [train] = normalizeFlyaiTransport([item], 'train');
  assert.equal(train.totalPrice, 400);
  assert.equal(train.provider, '飞猪 FlyAI');
  assert.equal(train.bookingUrl, 'https://example.com/book');
  assert.equal(train.trainNumber, 'G1');
  assert.equal(train.departureAt, '2026-10-09T08:00:00');
  assert.equal(train.priceComplete, false);
});

test('FlyAI flight detail preserves terminals and cabin while leaving absent aircraft, meals and bags unknown', () => {
  const row = { ticketPrice: '710', journeys: [{ segments: [{ depDateTime: '2026-10-09 08:00:00', arrDateTime: '2026-10-09 10:00:00',
    depStationName: '虹桥机场', depStationCode: 'SHA', depTerm: 'T1', arrStationName: '宝安机场', arrStationCode: 'SZX', arrTerm: 'T3',
    marketingTransportName: '春秋', marketingTransportNo: '9C8955', seatClassName: '经济舱', duration: '120' }] }] };
  const [flight] = normalizeFlyaiTransport([row], 'flight');
  assert.equal(flight.airlineCode, '9C');
  assert.equal(flight.flightSegments[0].departureTerminal, 'T1');
  assert.equal(flight.flightSegments[0].arrivalTerminal, 'T3');
  assert.equal(flight.flightSegments[0].cabinClass, '经济舱');
  assert.equal(flight.flightSegments[0].aircraftModel, null);
  assert.equal(flight.flightSegments[0].mealIncluded, null);
  assert.equal(flight.flightSegments[0].baggage.checkedPieces, null);
});

test('Tuniu train fare is selected from a seat with actual availability', () => {
  const [offer] = normalizeTuniuTrains({ data: [{ trainNum: 'G11', departStationName: '上海虹桥', destStationName: '深圳北',
    trainType: 'direct', departureTime: '2026-10-09 08:00', arrivalTime: '2026-10-09 15:00',
    price: { edzPrice: '320', ydzPrice: '520' }, seatAvailable: { edzNum: 0, ydzNum: 2 } }] }, '2026-10-09');
  assert.equal(offer.totalPrice, 520);
  assert.equal(offer.seatClass, '一等座');
  assert.equal(offer.seatsAvailable, 2);
});

test('Tuniu ticket search preserves starting price and its actual price date', async () => {
  const runner = async () => ({ success: true, result: { scenic_name: '世界之窗', tickets: [{ productId: 123, resId: 'a',
    startPrice: '50', departsDate: '2026-10-01', startDate: '2026-10-01', endDate: '2026-10-30', resName: '成人票' }] } });
  const [offer] = await searchTuniuTickets('世界之窗', '2026-10-09', runner);
  assert.equal(offer.price, 50);
  assert.equal(offer.startingPrice, true);
  assert.equal(offer.priceDate, '2026-10-01');
  assert.equal(offer.validForDate, '2026-10-09');
});
