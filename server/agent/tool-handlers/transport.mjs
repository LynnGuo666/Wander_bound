import { toolError } from '../definitions.mjs';
import { addDays } from '../request.mjs';

export async function searchTransport(ctx, args = {}) {
  const { state, providers, providerPriority = {}, startDate, memory, warnings } = ctx;
  if (!state.originDone) { return toolError('prerequisite', '请先调用 resolve_origin'); }
  if (!state.destination) { return toolError('missing_destination', '请先确定目的地'); }
  const travelEndDate = addDays(startDate, state.days - 1);
  const sources = [
    { provider: 'flyai', kind: 'flight', fn: providers.searchFlyaiTransport },
    { provider: 'flyai', kind: 'train', fn: providers.searchFlyaiTransport },
    { provider: 'tuniu', kind: 'flight', fn: providers.searchTuniuTransport },
    { provider: 'tuniu', kind: 'train', fn: providers.searchTuniuTransport },
    { provider: 'duffel', kind: 'flight', fn: (_kind, from, to, date) => providers.searchDuffelFlights(from, to, date) },
    { provider: 'rail12306', kind: 'train', fn: (_kind, from, to, date) => providers.searchRailTickets(from, to, date) },
  ].filter(source => typeof source.fn === 'function' && state.providerStatus[source.provider]?.configured)
    .sort((a, b) => {
      const order = a.kind === 'train' ? providerPriority.trains : providerPriority.flights;
      const rank = source => order?.indexOf(source.provider) ?? -1;
      return (rank(a) < 0 ? 99 : rank(a)) - (rank(b) < 0 ? 99 : rank(b));
    });
  const tasks = sources.flatMap(source => [
    { ...source, direction: 'outbound', invoke: () => source.fn(source.kind, state.originCity, state.destination, startDate) },
    { ...source, direction: 'return', invoke: () => source.fn(source.kind, state.destination, state.originCity, travelEndDate) },
  ]);
  const outcomes = new Array(tasks.length);
  let nextTask = 0;
  await Promise.all(Array.from({ length: Math.min(2, tasks.length) }, async () => {
    while (nextTask < tasks.length) {
      const index = nextTask++;
      try { outcomes[index] = { status: 'fulfilled', value: await tasks[index].invoke() }; }
      catch (reason) { outcomes[index] = { status: 'rejected', reason }; }
    }
  }));
  const validOffers = found => Array.isArray(found) ? found.filter(offer => offer?.id
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(offer.departureAt || '')
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(offer.arrivalAt || '')
    && ((offer.totalPrice === null && offer.currency === null) || (typeof offer.totalPrice === 'number' && Number.isFinite(offer.totalPrice) && offer.totalPrice >= 0 && offer.currency))) : [];
  tasks.forEach((task, index) => {
    const outcome = outcomes[index];
    const status = state.providerStatus[task.provider];
    if (outcome.status === 'rejected') {
      status.error = true;
      status.result = String(outcome.reason?.message || '查询失败').slice(0, 160);
      warnings.push(`${status.label} ${task.kind === 'train' ? '火车' : '航班'}查询失败`);
      return;
    }
    const offers = validOffers(outcome.value).map(offer => ({ ...offer, sourceId: task.provider }));
    if (offers.length) status.result = 'ok';
    else if (!status.result) status.result = '本次无报价';
    if (task.kind === 'flight') state[task.direction === 'outbound' ? 'flights' : 'returnFlights'].push(...offers);
    else state[task.direction === 'outbound' ? 'trains' : 'returnTrains'].push(...offers);
  });
  for (const provider of new Set(tasks.map(task => task.provider))) {
    const settled = tasks.map((task, index) => task.provider === provider ? outcomes[index] : null).filter(Boolean);
    const failed = settled.filter(item => item.status === 'rejected').length;
    state.providerStatus[provider].error = failed === settled.length;
    state.providerStatus[provider].partialError = failed > 0 && failed < settled.length;
  }
  state.transportDone = true;
  const compactOffer = offer => ({ id: offer.id, provider: offer.provider, departureAt: offer.departureAt, arrivalAt: offer.arrivalAt, totalPrice: offer.totalPrice, currency: offer.currency, stops: offer.stops });
  return { ok: true, originCity: state.originCity, preference: memory.transportPreference, avoidRedEye: memory.avoidRedEye,
    sourcePriority: { flights: providerPriority.flights || [], trains: providerPriority.trains || [] },
    outboundFlights: state.flights.slice(0, 20).map(compactOffer), returnFlights: state.returnFlights.slice(0, 20).map(compactOffer),
    outboundTrains: state.trains.slice(0, 20).map(compactOffer), returnTrains: state.returnTrains.slice(0, 20).map(compactOffer) };
}
