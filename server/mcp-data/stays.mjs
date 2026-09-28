import { createRequestProviders } from '../providers.mjs';
import { city, date, days } from './validation.mjs';

export async function searchStays(input, credentials = {}, providers = createRequestProviders(credentials)) {
  const name = city(input.city);
  const area = input.area ? city(input.area, '区域') : '';
  const checkInDate = date(input.checkInDate);
  const stayNights = days(input.stayNights);
  const budget = Number.isFinite(input.budget) && input.budget > 0 ? input.budget : 600;
  const hotels = await providers.searchDidaHotels(name, area, checkInDate, stayNights, budget);
  return { ok: true, hotels, source: '道旅 Docker MCP', configured: providers.providerAvailability().dida.configured };
}
