import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('../node_modules/.bin/', import.meta.url));
const MAX_OUTPUT = 2_000_000;

export function runCli(binary, args, { timeoutMs = 18000 } = {}) {
  if (!['tuniu', 'flyai'].includes(binary)) throw new Error('未允许的供应商命令');
  return new Promise((resolve, reject) => {
    const child = spawn(`${BIN}${binary}`, args, { shell: false, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    let finished = false;
    const timeout = setTimeout(() => child.kill('SIGKILL'), timeoutMs);
    function append(current, chunk) {
      const next = current + chunk.toString('utf8');
      if (next.length > MAX_OUTPUT) child.kill('SIGKILL');
      return next.slice(0, MAX_OUTPUT + 1);
    }
    child.stdout.on('data', chunk => { stdout = append(stdout, chunk); });
    child.stderr.on('data', chunk => { stderr = append(stderr, chunk); });
    child.on('error', error => { if (!finished) { finished = true; clearTimeout(timeout); reject(error); } });
    child.on('close', code => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);
      if (code !== 0 || stdout.length > MAX_OUTPUT) return reject(new Error(`${binary} 调用失败（退出码 ${code ?? '超时'}）：${stderr.slice(0, 180)}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error(`${binary} 返回非 JSON 数据`)); }
    });
  });
}

export function unwrapTuniu(payload) {
  if (payload?.success === false) throw new Error(`途牛调用失败：${payload.error?.message || '未知错误'}`);
  let value = payload?.result ?? payload;
  if (value?.isError) throw new Error('途牛 MCP 返回工具错误');
  if (value?.structuredContent && typeof value.structuredContent === 'object') value = value.structuredContent;
  if (Array.isArray(value?.content)) {
    const text = value.content.find(item => item?.type === 'text')?.text;
    if (!text) throw new Error('途牛 MCP 没有文本结果');
    try { value = JSON.parse(text); } catch { throw new Error('途牛 MCP 返回非 JSON 文本'); }
  }
  if (value?.successCode === false) throw new Error('途牛查询未成功');
  return value;
}

export function unwrapFlyai(payload) {
  if (payload?.status !== 0) throw new Error(`飞猪查询失败：${String(payload?.message || '未知错误').slice(0, 100)}`);
  return Array.isArray(payload?.data?.itemList) ? payload.data.itemList : [];
}

function isoLocal(value) {
  const match = String(value || '').match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
  return match ? `${match[1]}T${match[2]}:00` : null;
}

function price(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const text = String(value).replace(/[¥￥,\s]/g, '');
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function normalizeFlyaiTransport(rows, kind) {
  return rows.flatMap((item, index) => {
    const journey = item.journeys?.[0];
    const segments = journey?.segments;
    if (!Array.isArray(segments) || !segments.length) return [];
    const first = segments[0];
    const last = segments.at(-1);
    const departureAt = isoLocal(first.depDateTime);
    const arrivalAt = isoLocal(last.arrDateTime);
    const totalPrice = price(item.ticketPrice ?? item.adultPrice ?? item.price);
    if (!departureAt || !arrivalAt || arrivalAt <= departureAt) return [];
    const number = segments.map(segment => segment.marketingTransportNo).filter(Boolean).join(' · ');
    const common = {
      id: `flyai-${kind}-${item.id || `${departureAt}-${number}-${index}`}`, provider: '飞猪 FlyAI',
      departureAt, arrivalAt, totalPrice, currency: totalPrice === null ? null : 'CNY', stops: Math.max(0, segments.length - 1),
      origin: first.depStationName || first.depCityName || '', destination: last.arrStationName || last.arrCityName || '',
      bookingUrl: /^https:\/\//.test(item.jumpUrl || '') ? item.jumpUrl : null,
      priceBasis: totalPrice === null ? '价格请在供应商页面查看' : '供应商票价，税费及行李待核', priceComplete: false,
    };
    return [kind === 'flight' ? { ...common, airline: first.marketingTransportName || '', flightNumber: number } : { ...common, trainNumber: number, seatClass: first.seatClassName || '' }];
  });
}

export function normalizeTuniuFlights(payload, date) {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return rows.flatMap((item, index) => {
    const departureAt = isoLocal(item.departureTime?.includes('-') ? item.departureTime : `${date} ${item.departureTime || ''}`);
    const arrivalAt = isoLocal(item.arrivalTime?.includes('-') ? item.arrivalTime : `${date} ${item.arrivalTime || ''}`);
    const base = price(item.basePrice);
    const tax = price(item.totalTax);
    if (!departureAt || !arrivalAt || arrivalAt <= departureAt || base === null || tax === null) return [];
    const flightNumber = String(item.flightNumber || '').trim();
    if (!flightNumber) return [];
    return [{ id: `tuniu-flight-${date}-${flightNumber}-${index}`, provider: '途牛 MCP', airline: item.airlineCompany || '', flightNumber,
      departureAt, arrivalAt, origin: item.departureAirport || '', destination: item.arrivalAirport || '',
      stops: /直飞|直达/.test(item.type || '') ? 0 : 1, totalPrice: base + tax, currency: 'CNY', priceBasis: '基价及税费', priceComplete: true }];
  });
}

export function normalizeTuniuTrains(payload, date) {
  const rows = Array.isArray(payload?.data) ? payload.data : [];
  return rows.flatMap((item, index) => {
    const trainNumber = String(item.trainNum || item.trainNo || item.trainNumber || '').trim();
    const departureAt = isoLocal(item.departureTime?.includes('-') ? item.departureTime : `${date} ${item.departureTime || ''}`);
    const arrivalAt = isoLocal(item.arrivalTime?.includes('-') ? item.arrivalTime : `${date} ${item.arrivalTime || ''}`);
    const seats = [
      ['edzPrice', 'edzNum', '二等座'], ['ydzPrice', 'ydzNum', '一等座'], ['swzPrice', 'swzNum', '商务座'],
      ['yzPrice', 'yzNum', '硬座'], ['ywPrice', 'ywNum', '硬卧'], ['rwPrice', 'rwNum', '软卧'],
    ].flatMap(([fare, count, label]) => {
      const totalPrice = price(item.price?.[fare]);
      const available = item.seatAvailable?.[count];
      return totalPrice !== null && Number.isFinite(available) && available > 0 ? [{ totalPrice, available, label }] : [];
    }).sort((a, b) => a.totalPrice - b.totalPrice);
    if (!trainNumber || !departureAt || !arrivalAt || arrivalAt <= departureAt || !seats.length) return [];
    const seat = seats[0];
    return [{ id: `tuniu-train-${date}-${trainNumber}-${index}`, provider: '途牛 MCP', trainNumber,
      departureAt, arrivalAt, origin: item.departStationName || '', destination: item.destStationName || '',
      stops: item.trainType === 'direct' ? 0 : 1, totalPrice: seat.totalPrice, currency: 'CNY',
      seatClass: seat.label, seatsAvailable: seat.available, priceBasis: `${seat.label}参考价`, priceComplete: true }];
  });
}

export function normalizeFlyaiAttractions(rows) {
  return rows.flatMap(item => {
    const name = String(item.name || '').trim();
    if (!name || !item.id || !item.ticketInfo || (!item.ticketInfo.ticketName && !item.ticketInfo.price)) return [];
    const amount = price(item.ticketInfo?.price);
    return [{ provider: '飞猪 FlyAI', providerPlaceId: String(item.id), name, address: String(item.address || ''),
      lat: Number(item.latitude) || null, lng: Number(item.longitude) || null,
      productName: String(item.ticketInfo?.ticketName || ''), price: amount, priceDate: item.ticketInfo?.priceDate || null,
      currency: amount === null ? null : 'CNY', bookingUrl: /^https:\/\//.test(item.jumpUrl || '') ? item.jumpUrl : null,
      imageUrl: /^https:\/\//.test(item.mainPic || '') ? item.mainPic : null }];
  });
}

export async function searchFlyai(kind, origin, destination, date, runner = runCli) {
  const command = kind === 'train' ? 'search-train' : 'search-flight';
  const payload = await runner('flyai', [command, '--origin', origin, '--destination', destination, '--dep-date', date, '--sort-type', '3']);
  return normalizeFlyaiTransport(unwrapFlyai(payload), kind);
}

export async function searchTuniu(kind, origin, destination, date, runner = runCli) {
  const flight = kind === 'flight';
  const payload = unwrapTuniu(await runner('tuniu', ['call', flight ? 'flight' : 'train', flight ? 'searchLowestPriceFlight' : 'searchLowestPriceTrain',
    '-a', JSON.stringify({ departureCityName: origin, arrivalCityName: destination, departureDate: date })]));
  return flight ? normalizeTuniuFlights(payload, date) : normalizeTuniuTrains(payload, date);
}

export async function searchFlyaiAttractions(city, keyword = '', runner = runCli) {
  const args = ['search-poi', '--city-name', city];
  if (keyword) args.push('--keyword', keyword);
  const payload = await runner('flyai', args);
  return normalizeFlyaiAttractions(unwrapFlyai(payload));
}

export async function searchTuniuTickets(name, date, runner = runCli) {
  const payload = unwrapTuniu(await runner('tuniu', ['call', 'ticket', 'query_cheapest_tickets', '-a', JSON.stringify({ scenic_name: name, depart_date: date })]));
  const rows = Array.isArray(payload?.tickets) ? payload.tickets : [];
  return rows.flatMap((item, index) => {
    const productName = String(item.resName || item.ticketTypeName || '').trim();
    const amount = price(item.startPrice);
    if (!productName || amount === null) return [];
    if (date && ((item.startDate && date < item.startDate) || (item.endDate && date > item.endDate))) return [];
    return [{ provider: '途牛 MCP', providerPlaceId: String(item.productId || ''), name, productName, price: amount,
      currency: 'CNY', priceDate: item.departsDate || null, validForDate: date || null, startingPrice: true,
      bookingUrl: null, id: `tuniu-ticket-${item.productId || index}-${item.resId || ''}` }];
  });
}
