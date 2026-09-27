function minutes(iso) {
  const match = /^PT(?:(\d+)H)?(?:(\d+)M)?$/.exec(iso || '');
  return match ? Number(match[1] || 0) * 60 + Number(match[2] || 0) : null;
}

function flag(value) { return value === true || value === 'true' ? true : value === false || value === 'false' ? false : null; }

function policy(value) {
  if (!value || typeof value !== 'object') return null;
  return { allowed: flag(value.allowed), penaltyAmount: value.penalty_amount == null ? null : Number(value.penalty_amount), penaltyCurrency: value.penalty_currency || null };
}

export function normalizeDuffelOffers(offers, originCity, destinationCity) {
  return offers.slice(0, 30).map(offer => {
    const slice = offer.slices?.[0];
    const segments = slice?.segments || [];
    if (!segments.length) return null;
    const flightSegments = segments.map(segment => {
      const passenger = segment.passengers?.[0];
      const bags = passenger?.baggages;
      const count = type => Array.isArray(bags) ? bags.filter(bag => bag.type === type).reduce((sum, bag) => sum + (Number(bag.quantity) || 0), 0) : null;
      const amenities = passenger?.cabin?.amenities;
      return {
        marketingCarrier: segment.marketing_carrier?.name || null,
        marketingCarrierCode: segment.marketing_carrier?.iata_code || null,
        flightNumber: segment.marketing_carrier_flight_number == null ? null : `${segment.marketing_carrier?.iata_code || ''}${segment.marketing_carrier_flight_number}`,
        operatingCarrier: segment.operating_carrier?.name || null,
        operatingCarrierCode: segment.operating_carrier?.iata_code || null,
        operatingFlightNumber: segment.operating_carrier_flight_number == null ? null : `${segment.operating_carrier?.iata_code || ''}${segment.operating_carrier_flight_number}`,
        aircraftModel: segment.aircraft?.name || null, aircraftCode: segment.aircraft?.iata_code || null,
        cabinClass: passenger?.cabin_class_marketing_name || passenger?.cabin_class || null,
        mealIncluded: null,
        departureAirport: segment.origin?.name || null, departureCode: segment.origin?.iata_code || null, departureTerminal: segment.origin_terminal || null,
        arrivalAirport: segment.destination?.name || null, arrivalCode: segment.destination?.iata_code || null, arrivalTerminal: segment.destination_terminal || null,
        departureAt: segment.departing_at || null, arrivalAt: segment.arriving_at || null, durationMinutes: minutes(segment.duration),
        baggage: { carryOnPieces: count('carry_on'), checkedPieces: count('checked'), weightKg: null },
        amenities: amenities ? { wifi: flag(amenities.wifi?.available), wifiCost: amenities.wifi?.cost || null,
          power: flag(amenities.power?.available), seatType: amenities.seat?.type || null, legroom: amenities.seat?.legroom || null,
          seatPitchInches: amenities.seat?.pitch || null } : null,
      };
    });
    const first = flightSegments[0];
    const last = flightSegments.at(-1);
    const fareBags = first.baggage;
    return {
      id: offer.id, provider: 'Duffel', airline: first.operatingCarrier || first.marketingCarrier || '', airlineCode: first.operatingCarrierCode || first.marketingCarrierCode,
      flightNumber: flightSegments.map(segment => segment.flightNumber).filter(Boolean).join(' · '), flightSegments,
      departureAt: first.departureAt || '', arrivalAt: last.arrivalAt || '',
      origin: first.departureCode || null, destination: last.arrivalCode || null,
      stops: Math.max(0, segments.length - 1), totalPrice: Number(offer.total_amount), currency: offer.total_currency,
      priceComplete: true, priceBasis: '供应商总价', fareBrand: slice?.fare_brand_name || null,
      basePrice: offer.base_amount == null ? null : Number(offer.base_amount), taxAmount: offer.tax_amount == null ? null : Number(offer.tax_amount),
      changePolicy: policy(offer.conditions?.change_before_departure), refundPolicy: policy(offer.conditions?.refund_before_departure),
      mealIncluded: null, baggage: fareBags, expiresAt: offer.expires_at,
    };
  }).filter(flight => flight && Number.isFinite(flight.totalPrice));
}

export async function searchDuffelFlights(originCity, destinationCity, date, key = process.env.DUFFEL_API_KEY) {
  if (!key || originCity === destinationCity) return [];
  // Duffel 只接受 IATA 机场码；项目不再维护手编的城市映射表，
  // 在接入真实机场码数据源之前明确失败，而不是猜一个码发起请求。
  throw new Error('缺少城市到 IATA 机场码的真实数据源，Duffel 暂不可用');
}
