import { CITY_AIRPORTS } from '../../shared/catalog.mjs';
import { controllerFor } from './http-client.mjs';

export async function searchDuffelFlights(originCity, destinationCity, date, key = process.env.DUFFEL_API_KEY) {
  if (!key || !CITY_AIRPORTS[originCity] || !CITY_AIRPORTS[destinationCity] || originCity === destinationCity) return [];
  const response = await fetch('https://api.duffel.com/air/offer_requests', {
    method: 'POST', signal: controllerFor(15000),
    headers: {
      Authorization: `Bearer ${key}`,
      'Duffel-Version': 'v2', 'Content-Type': 'application/json', Accept: 'application/json',
    },
    body: JSON.stringify({ data: {
      slices: [{ origin: CITY_AIRPORTS[originCity], destination: CITY_AIRPORTS[destinationCity], departure_date: date }],
      passengers: [{ type: 'adult' }], cabin_class: 'economy', max_connections: 1,
    } }),
  });
  if (!response.ok) throw new Error(`Duffel HTTP ${response.status}`);
  const payload = await response.json();
  return (payload.data?.offers || []).slice(0, 30).map(offer => {
    const segments = offer.slices?.[0]?.segments || [];
    return {
      id: offer.id, provider: 'Duffel', airline: segments[0]?.operating_carrier?.name || segments[0]?.marketing_carrier?.name || '航空公司',
      flightNumber: segments.map(segment => `${segment.marketing_carrier?.iata_code || ''}${segment.marketing_carrier_flight_number || ''}`).join(' · '),
      departureAt: segments[0]?.departing_at || '', arrivalAt: segments.at(-1)?.arriving_at || '',
      origin: segments[0]?.origin?.iata_code || CITY_AIRPORTS[originCity],
      destination: segments.at(-1)?.destination?.iata_code || CITY_AIRPORTS[destinationCity],
      stops: Math.max(0, segments.length - 1), totalPrice: Number(offer.total_amount), currency: offer.total_currency,
      priceComplete: true, priceBasis: '供应商总价',
      expiresAt: offer.expires_at,
    };
  }).filter(flight => Number.isFinite(flight.totalPrice));
}
