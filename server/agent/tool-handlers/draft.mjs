import { assemblePlan } from '../../../shared/planner.mjs';
import { toolError } from '../definitions.mjs';
import { planInvariant } from '../plan-output.mjs';

export async function draftPlan(ctx, args = {}) {
  const { state, memory, providerPriority, startDate, cache, internal } = ctx;
  if (!state.placesDone || !state.originDone || !state.transportDone || !state.staysDone) { return toolError('prerequisite', '请先完成位置、地点、交通和住宿查询'); }
  if (state.drafts >= 2) { return toolError('draft_limit', '最多草拟两次'); }
  const available = state.places
    .filter(place => place?.id && Number.isFinite(place.lat) && Number.isFinite(place.lng))
    .filter(place => !memory.visitedPlaces.some(visited => visited.id === place.id || (visited.name === place.name && visited.city === state.destination)));
  const requested = args.placeIds;
  if (!Array.isArray(requested) || requested.some(id => typeof id !== 'string') || new Set(requested).size !== requested.length) {
    return toolError('invalid_places', 'placeIds 必须是无重复的地点 ID 数组');
  }
  if (!requested.length && !internal && available.length) { return toolError('missing_selection', '请从候选地点中选出具体 ID'); }
  if (requested.some(id => !available.some(place => place.id === id))) { return toolError('unverified_place', '包含未查询或已到访的地点'); }
  const target = state.days === 1 ? 2 : state.days === 2 ? 4 : 4 + (state.days - 2) * 3;
  if (requested.length && requested.length < Math.min(target, available.length)) { return toolError('too_few_places', `请选至少 ${Math.min(target, available.length)} 个地点`); }
  const draft = assemblePlan({ destination: state.destination, originCity: state.originCity, startDate, days: state.days, memory, places: state.places, flights: state.flights, returnFlights: state.returnFlights, trains: state.trains, returnTrains: state.returnTrains, hotels: state.hotels, providerStatus: state.providerStatus, providerPriority, desiredInterests: state.desiredInterests, proposedPlaceIds: requested });
  draft.itinerary = draft.itinerary.map(day => ({ ...day, city: state.destination,
    requiredStay: state.requiredStays.some(stay => stay.city === state.destination && day.date >= stay.from && day.date <= stay.to) }));
  const invalid = planInvariant(draft, memory, available);
  if (invalid) { return toolError('invalid_plan', invalid); }
  state.plan = draft;
  state.attractionsDone = false;
  state.diningDone = false;
  state.groundDone = false;
  cache.delete('search_attractions');
  cache.delete('search_dining');
  cache.delete('explore_ground');
  state.drafts += 1;
  return { ok: true, days: draft.itinerary.map(day => ({ day: day.day, date: day.date, places: day.stops.map(stop => stop.name), starts: day.stops.map(stop => stop.start) })), stayArea: draft.stayArea?.name, flightQuotes: draft.flights.length, returnFlightQuotes: draft.returnFlights.length, trainQuotes: draft.trains.length, returnTrainQuotes: draft.returnTrains.length, recommendedReturnFlightId: draft.recommendedReturnFlightId, hotelQuotes: draft.hotels.length };
}
