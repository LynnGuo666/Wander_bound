import { runCli } from './run-cli.mjs';
import { isoLocal, price } from './normalize.mjs';

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

export async function searchTuniu(kind, origin, destination, date, runner = runCli) {
  const flight = kind === 'flight';
  const payload = unwrapTuniu(await runner('tuniu', ['call', flight ? 'flight' : 'train', flight ? 'searchLowestPriceFlight' : 'searchLowestPriceTrain',
    '-a', JSON.stringify({ departureCityName: origin, arrivalCityName: destination, departureDate: date })]));
  return flight ? normalizeTuniuFlights(payload, date) : normalizeTuniuTrains(payload, date);
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
