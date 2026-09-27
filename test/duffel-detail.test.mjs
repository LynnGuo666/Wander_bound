import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDuffelOffers } from '../server/providers/duffel.mjs';

test('Duffel offer exposes actual aircraft, operating carrier, baggage pieces and fare rules', () => {
  const [flight] = normalizeDuffelOffers([{ id: 'offer-1', total_amount: '420', total_currency: 'CNY', base_amount: '350', tax_amount: '70',
    conditions: { change_before_departure: { allowed: true, penalty_amount: '50', penalty_currency: 'CNY' }, refund_before_departure: { allowed: false } },
    slices: [{ fare_brand_name: 'Basic', segments: [{ departing_at: '2026-10-09T08:00:00', arriving_at: '2026-10-09T10:00:00', duration: 'PT02H00M',
      origin: { name: '虹桥', iata_code: 'SHA' }, origin_terminal: '1', destination: { name: '宝安', iata_code: 'SZX' }, destination_terminal: '3',
      marketing_carrier: { name: '营销航司', iata_code: 'MU' }, marketing_carrier_flight_number: '1234',
      operating_carrier: { name: '承运航司', iata_code: 'FM' }, operating_carrier_flight_number: '9012',
      aircraft: { name: 'Airbus A320', iata_code: '320' },
      passengers: [{ cabin_class_marketing_name: 'Economy', baggages: [{ type: 'checked', quantity: 1 }, { type: 'carry_on', quantity: 1 }],
        cabin: { amenities: { wifi: { available: 'true', cost: 'free' }, power: { available: 'false' } } } }] }] }] }], '上海', '深圳');
  assert.equal(flight.airline, '承运航司');
  assert.equal(flight.flightSegments[0].aircraftModel, 'Airbus A320');
  assert.equal(flight.flightSegments[0].operatingFlightNumber, 'FM9012');
  assert.equal(flight.flightSegments[0].baggage.checkedPieces, 1);
  assert.equal(flight.flightSegments[0].amenities.wifi, true);
  assert.equal(flight.flightSegments[0].mealIncluded, null);
  assert.deepEqual(flight.changePolicy, { allowed: true, penaltyAmount: 50, penaltyCurrency: 'CNY' });
  assert.equal(flight.refundPolicy.allowed, false);
});
