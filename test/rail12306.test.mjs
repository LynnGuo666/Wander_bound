import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeRailDirect, normalizeRailTransfers, searchRailTickets } from '../server/providers/rail12306.mjs';

const direct = { train_no: 'rail-id', start_train_code: 'G1', start_date: '2026-10-01', arrive_date: '2026-10-01',
  start_time: '08:00', arrive_time: '18:00', from_station: '长春', to_station: '柳州', lishi: '10:00',
  prices: [{ seat_name: '二等座', price: 600, num: '无' }, { seat_name: '一等座', price: 950, num: '2' }] };

test('12306 direct train selects only an actually available seat and retains all seat states', () => {
  const [train] = normalizeRailDirect([direct]);
  assert.equal(train.totalPrice, 950);
  assert.equal(train.seatClass, '一等座');
  assert.equal(train.seatsAvailable, 2);
  assert.equal(train.seatOptions[0].availability, '无');
  assert.equal(train.provider, '12306 MCP（社区）');
});

test('12306 transfer preserves both train legs and a cross-station change', () => {
  const [train] = normalizeRailTransfers([{ start_date: '2026-10-01', middle_station_name: '北京朝阳-北京西', same_station: false,
    wait_time: '1小时41分钟', ticketList: [direct, { ...direct, train_no: 'rail-id-2', start_train_code: 'D919',
      start_time: '20:27', arrive_date: '2026-10-02', arrive_time: '09:10', from_station: '北京西', to_station: '柳州',
      prices: [{ seat_name: '动卧', price: 1700, num: '有' }] }] }]);
  assert.equal(train.trainSegments.length, 2);
  assert.equal(train.totalPrice, 2650);
  assert.equal(train.transfer.sameStation, false);
  assert.match(train.transfer.station, /北京朝阳/);
});

test('12306 adapter calls only get-tickets and falls back to interline when direct seats are scarce', async () => {
  const previous = process.env.TRAVEL_12306_MCP_URL;
  process.env.TRAVEL_12306_MCP_URL = 'http://127.0.0.1:4177/mcp';
  const calls = [];
  const fetchImpl = async (_url, request) => {
    const message = JSON.parse(request.body);
    calls.push(message.params.name);
    const rows = message.params.name === 'get-tickets' ? [direct] : [];
    return { ok: true, json: async () => ({ result: { content: [{ type: 'text', text: JSON.stringify(rows) }] } }) };
  };
  try {
    const trains = await searchRailTickets('长春', '柳州', '2026-10-01', { fetchImpl });
    assert.equal(trains.length, 1);
    assert.deepEqual(calls, ['get-tickets', 'get-interline-tickets']);
  } finally {
    if (previous === undefined) delete process.env.TRAVEL_12306_MCP_URL;
    else process.env.TRAVEL_12306_MCP_URL = previous;
  }
});
