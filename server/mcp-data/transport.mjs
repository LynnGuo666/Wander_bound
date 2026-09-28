import { createRequestProviders } from '../providers.mjs';
import { addDays, city, date, days } from './validation.mjs';

function validOffers(value) {
  return Array.isArray(value) ? value.filter(offer => offer?.id
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(offer.departureAt || '')
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(offer.arrivalAt || '')
    && ((offer.totalPrice === null && offer.currency === null)
      || (Number.isFinite(offer.totalPrice) && offer.totalPrice >= 0 && offer.currency))) : [];
}

export async function searchTransport(input, credentials = {}, providers = createRequestProviders(credentials)) {
  const originCity = city(input.originCity, '出发城市');
  const destination = city(input.destination, '目的地');
  const startDate = date(input.startDate);
  const travelDays = days(input.days);
  const priorities = input.priorities || {};
  const status = providers.providerAvailability();
  const sources = [
    { provider: 'flyai', kind: 'flight', fn: providers.searchFlyaiTransport },
    { provider: 'flyai', kind: 'train', fn: providers.searchFlyaiTransport },
    { provider: 'tuniu', kind: 'flight', fn: providers.searchTuniuTransport },
    { provider: 'tuniu', kind: 'train', fn: providers.searchTuniuTransport },
    { provider: 'duffel', kind: 'flight', fn: (_kind, from, to, day) => providers.searchDuffelFlights(from, to, day) },
    { provider: 'rail12306', kind: 'train', fn: (_kind, from, to, day) => providers.searchRailTickets(from, to, day) },
  ].filter(source => typeof source.fn === 'function' && status[source.provider]?.configured)
    .sort((a, b) => {
      const order = a.kind === 'train' ? priorities.trains : priorities.flights;
      const rank = source => { const index = order?.indexOf(source.provider) ?? -1; return index < 0 ? 99 : index; };
      return rank(a) - rank(b);
    });
  const tasks = sources.flatMap(source => [
    { ...source, direction: 'outbound', from: originCity, to: destination, day: startDate },
    { ...source, direction: 'return', from: destination, to: originCity, day: addDays(startDate, travelDays - 1) },
  ]);
  const results = new Array(tasks.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(2, tasks.length) }, async () => {
    while (cursor < tasks.length) {
      const index = cursor++;
      const task = tasks[index];
      try { results[index] = { offers: validOffers(await task.fn(task.kind, task.from, task.to, task.day)) }; }
      catch (error) { results[index] = { error: String(error?.message || '查询失败').slice(0, 160) }; }
    }
  }));
  const output = { ok: true, originCity, outboundFlights: [], returnFlights: [], outboundTrains: [], returnTrains: [],
    providerStatus: status, warnings: [] };
  tasks.forEach((task, index) => {
    const result = results[index];
    const source = status[task.provider];
    if (result.error) {
      source.result = result.error;
      output.warnings.push(`${source.label} ${task.kind === 'train' ? '火车' : '航班'}查询失败`);
    } else {
      if (result.offers.length) source.result = 'ok';
      else if (!source.result) source.result = '本次无报价';
      const field = `${task.direction}${task.kind === 'flight' ? 'Flights' : 'Trains'}`;
      output[field].push(...result.offers.map(offer => ({ ...offer, sourceId: task.provider })));
    }
  });
  for (const provider of new Set(tasks.map(task => task.provider))) {
    const relevant = tasks.map((task, index) => task.provider === provider ? results[index] : null).filter(Boolean);
    const failed = relevant.filter(item => item.error).length;
    status[provider].error = failed === relevant.length;
    status[provider].partialError = failed > 0 && failed < relevant.length;
  }
  return output;
}
