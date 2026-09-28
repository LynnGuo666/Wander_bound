import { createRequestProviders } from '../providers.mjs';
import { city, date } from './validation.mjs';

export async function searchAttractions(input, credentials = {}, providers = createRequestProviders(credentials)) {
  const name = city(input.city);
  if (!Array.isArray(input.places) || input.places.length > 7) throw new Error('景区列表无效');
  const places = input.places.map(place => ({ id: city(place.id, '景区 ID'), name: city(place.name, '景区名'), visitDate: date(place.visitDate) }));
  const found = await providers.searchAttractionProducts(name, places);
  const names = new Set(places.map(place => place.name));
  const rank = item => {
    const order = input.priorities?.attractions || [];
    const source = item.sourceId || (/飞猪/.test(item.provider) ? 'flyai' : /途牛/.test(item.provider) ? 'tuniu' : '');
    const index = order.indexOf(source);
    return index < 0 ? order.length : index;
  };
  const offers = (Array.isArray(found) ? found : []).filter(item => item?.provider && names.has(item.name)
    && (item.price === null || (Number.isFinite(item.price) && item.price >= 0))
    && (!item.bookingUrl || /^https:\/\//.test(item.bookingUrl))).slice(0, 60).sort((a, b) => rank(a) - rank(b));
  return { ok: true, offers, source: 'OTA Docker MCP' };
}
