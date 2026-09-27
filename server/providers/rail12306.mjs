const endpoint = () => process.env.TRAVEL_12306_MCP_URL;

export async function callRailMcp(method, params = {}, { fetchImpl = fetch, timeoutMs = 18000 } = {}) {
  if (!endpoint()) throw new Error('12306 MCP 未配置');
  const response = await fetchImpl(endpoint(), {
    method: 'POST', signal: AbortSignal.timeout(timeoutMs),
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  if (!response.ok) throw new Error(`12306 MCP HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error) throw new Error(`12306 MCP ${payload.error.code || 'error'}`);
  return payload.result;
}

export async function listRailMcpTools(options = {}) {
  const result = await callRailMcp('tools/list', {}, options);
  return Array.isArray(result?.tools) ? result.tools.map(tool => ({ name: tool.name, description: tool.description || '', inputSchema: tool.inputSchema || null })) : [];
}

async function query(name, args, options) {
  const result = await callRailMcp('tools/call', { name, arguments: args }, options);
  if (result?.isError) throw new Error('12306 MCP 查询失败');
  const text = result?.content?.find(item => item.type === 'text')?.text || '';
  if (/^Error:/i.test(text)) throw new Error(text.slice(0, 120));
  try { return JSON.parse(text); } catch { throw new Error('12306 MCP 返回非 JSON 数据'); }
}

function seats(prices) {
  return Array.isArray(prices) ? prices.flatMap(item => {
    const amount = Number(item.price);
    if (!item.seat_name || !Number.isFinite(amount) || amount < 0) return [];
    const availability = String(item.num || '未知');
    return [{ name: item.seat_name, price: amount, availability,
      available: availability === '有' || (/^\d+$/.test(availability) && Number(availability) > 0),
      count: /^\d+$/.test(availability) ? Number(availability) : null }];
  }) : [];
}

function leg(item) {
  const seatOptions = seats(item.prices);
  const selected = seatOptions.filter(seat => seat.available).sort((a, b) => a.price - b.price)[0] || null;
  return { trainNumber: item.start_train_code, origin: item.from_station, destination: item.to_station,
    departureAt: `${item.start_date}T${item.start_time}:00`, arrivalAt: `${item.arrive_date}T${item.arrive_time}:00`,
    duration: item.lishi || null, seatOptions, selectedSeat: selected,
    flags: Array.isArray(item.dw_flag) ? item.dw_flag : [] };
}

export function normalizeRailDirect(rows) {
  return Array.isArray(rows) ? rows.flatMap((item, index) => {
    if (!item.start_train_code || !item.start_date || !item.arrive_date || !item.start_time || !item.arrive_time) return [];
    const segment = leg(item);
    return [{ id: `rail12306-${item.start_date}-${item.train_no || item.start_train_code}-${index}`, provider: '12306 MCP（社区）',
      trainNumber: segment.trainNumber, departureAt: segment.departureAt, arrivalAt: segment.arrivalAt,
      origin: segment.origin, destination: segment.destination, stops: 0,
      totalPrice: segment.selectedSeat?.price ?? null, currency: segment.selectedSeat ? 'CNY' : null,
      seatClass: segment.selectedSeat?.name || null, seatsAvailable: segment.selectedSeat?.count ?? null,
      seatAvailability: segment.selectedSeat?.availability || '无可售席别', seatOptions: segment.seatOptions,
      trainSegments: [segment], transfer: null, trainFlags: segment.flags,
      priceBasis: segment.selectedSeat ? `${segment.selectedSeat.name}票价 · 预订前以 12306 为准` : '无可售席别', priceComplete: Boolean(segment.selectedSeat) }];
  }) : [];
}

export function normalizeRailTransfers(rows) {
  return Array.isArray(rows) ? rows.flatMap((item, index) => {
    if (!Array.isArray(item.ticketList) || item.ticketList.length < 2) return [];
    const segments = item.ticketList.map(leg);
    if (segments.some(segment => !segment.departureAt || !segment.arrivalAt)) return [];
    const priced = segments.every(segment => segment.selectedSeat);
    return [{ id: `rail12306-transfer-${item.start_date}-${item.first_train_no || index}-${item.second_train_no || index}`,
      provider: '12306 MCP（社区）', trainNumber: segments.map(segment => segment.trainNumber).join(' → '),
      departureAt: segments[0].departureAt, arrivalAt: segments.at(-1).arrivalAt,
      origin: segments[0].origin, destination: segments.at(-1).destination, stops: segments.length - 1,
      totalPrice: priced ? segments.reduce((sum, segment) => sum + segment.selectedSeat.price, 0) : null,
      currency: priced ? 'CNY' : null, seatClass: priced ? segments.map(segment => segment.selectedSeat.name).join(' / ') : null,
      seatsAvailable: priced && segments.every(segment => Number.isFinite(segment.selectedSeat.count)) ? Math.min(...segments.map(segment => segment.selectedSeat.count)) : null,
      seatAvailability: priced ? segments.map(segment => segment.selectedSeat.availability).join(' / ') : '部分航段无可售席别',
      trainSegments: segments, transfer: { station: item.middle_station_name || null, sameStation: item.same_station === true,
        waitTime: item.wait_time || null }, trainFlags: [...new Set(segments.flatMap(segment => segment.flags))],
      priceBasis: priced ? '各段可售席别票价之和 · 预订前以 12306 为准' : '部分航段无可售席别', priceComplete: priced }];
  }) : [];
}

export async function searchRailTickets(origin, destination, date, options = {}) {
  if (!origin || !destination || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return [];
  const args = { date, fromStation: origin, toStation: destination, format: 'json' };
  const [direct, interline] = await Promise.allSettled([
    query('get-tickets', { ...args, limitedNum: 30 }, options),
    query('get-interline-tickets', { ...args, limitedNum: 10 }, options),
  ]);
  if (direct.status === 'rejected' && interline.status === 'rejected') throw direct.reason;
  return [
    ...(direct.status === 'fulfilled' ? normalizeRailDirect(direct.value) : []),
    ...(interline.status === 'fulfilled' ? normalizeRailTransfers(interline.value) : []),
  ];
}
