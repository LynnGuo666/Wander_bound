import { runCli } from './run-cli.mjs';
import { isoLocal, price } from './normalize.mjs';

export function unwrapFlyai(payload) {
  if (payload?.status !== 0) throw new Error(`飞猪查询失败：${String(payload?.message || '未知错误').slice(0, 100)}`);
  return Array.isArray(payload?.data?.itemList) ? payload.data.itemList : [];
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
    const flightSegments = kind === 'flight' ? segments.map(segment => ({
      marketingCarrier: segment.marketingTransportName || null,
      marketingCarrierCode: /^[A-Z0-9]{2}(?=\d)/i.exec(segment.marketingTransportNo || '')?.[0] || null,
      flightNumber: segment.marketingTransportNo || null,
      operatingCarrier: null, operatingCarrierCode: null, operatingFlightNumber: null,
      aircraftModel: null, aircraftCode: null, mealIncluded: null,
      cabinClass: segment.seatClassName || null,
      departureAirport: segment.depStationName || null, departureCode: segment.depStationCode || null, departureTerminal: segment.depTerm || null,
      arrivalAirport: segment.arrStationName || null, arrivalCode: segment.arrStationCode || null, arrivalTerminal: segment.arrTerm || null,
      departureAt: isoLocal(segment.depDateTime), arrivalAt: isoLocal(segment.arrDateTime),
      durationMinutes: Number(segment.duration) || null,
      baggage: { carryOnPieces: null, checkedPieces: null, weightKg: null }, amenities: null,
    })) : undefined;
    const common = {
      id: `flyai-${kind}-${item.id || `${departureAt}-${number}-${index}`}`, provider: '飞猪 FlyAI',
      departureAt, arrivalAt, totalPrice, currency: totalPrice === null ? null : 'CNY', stops: Math.max(0, segments.length - 1),
      origin: first.depStationName || first.depCityName || '', destination: last.arrStationName || last.arrCityName || '',
      bookingUrl: /^https:\/\//.test(item.jumpUrl || '') ? item.jumpUrl : null,
      priceBasis: totalPrice === null ? '价格请在供应商页面查看' : '供应商票价，税费及行李待核', priceComplete: false,
    };
    return [kind === 'flight' ? { ...common, airline: first.marketingTransportName || '', airlineCode: flightSegments[0]?.marketingCarrierCode,
      flightNumber: number, flightSegments, fareBrand: null, changePolicy: null, refundPolicy: null, mealIncluded: null,
      baggage: { carryOnPieces: null, checkedPieces: null, weightKg: null } } : { ...common, trainNumber: number, seatClass: first.seatClassName || '' }];
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

export async function searchFlyaiAttractions(city, keyword = '', runner = runCli) {
  const args = ['search-poi', '--city-name', city];
  if (keyword) args.push('--keyword', keyword);
  const payload = await runner('flyai', args);
  return normalizeFlyaiAttractions(unwrapFlyai(payload));
}
