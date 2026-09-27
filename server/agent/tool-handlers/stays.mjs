import { assemblePlan } from '../../../shared/planner.mjs';
import { toolError } from '../definitions.mjs';

export async function searchStays(ctx, args = {}) {
  const { state, providers, startDate, memory, warnings } = ctx;
  if (!state.placesDone) { return toolError('prerequisite', '请先调用 discover_places'); }
  const preliminary = assemblePlan({ destination: state.destination, originCity: state.originCity, startDate, days: state.days, memory, places: state.places, desiredInterests: state.desiredInterests });
  const area = preliminary.stayArea?.name || '';
  try {
    const found = state.providerStatus.dida?.configured
      ? await providers.searchDidaHotels(state.destination, area, startDate, Math.max(1, state.days - 1), memory.hotelNightBudget) : [];
    state.hotels = Array.isArray(found) ? found.filter(hotel => hotel?.id && hotel.name) : [];
    state.providerStatus.dida.result = state.providerStatus.dida.configured ? (state.hotels.length ? 'ok' : '本次无酒店报价') : '未配置';
  } catch (error) { state.hotels = []; state.providerStatus.dida.result = error.message; state.providerStatus.dida.error = true; warnings.push('酒店查询失败'); }
  state.staysDone = true;
  return { ok: true, suggestedArea: area, brands: memory.hotelBrands, budget: memory.hotelNightBudget, hotels: state.hotels.slice(0, 20).map(hotel => ({ id: hotel.id, name: hotel.name, displayPrice: hotel.displayPrice, priceBasis: hotel.priceBasis, currency: hotel.currency })) };
}
