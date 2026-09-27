import { toolError } from './definitions.mjs';

const loaders = {
  ask_question: () => import('./tool-handlers/basic.mjs').then(module => module.askQuestion),
  set_trip_spec: () => import('./tool-handlers/basic.mjs').then(module => module.setTripSpec),
  resolve_origin: () => import('./tool-handlers/basic.mjs').then(module => module.resolveOrigin),
  discover_places: () => import('./tool-handlers/basic.mjs').then(module => module.discoverPlaces),
  search_transport: () => import('./tool-handlers/transport.mjs').then(module => module.searchTransport),
  search_stays: () => import('./tool-handlers/stays.mjs').then(module => module.searchStays),
  draft_plan: () => import('./tool-handlers/draft.mjs').then(module => module.draftPlan),
  search_attractions: () => import('./tool-handlers/enrichment.mjs').then(module => module.searchAttractions),
  search_dining: () => import('./tool-handlers/enrichment.mjs').then(module => module.searchDining),
  explore_ground: () => import('./tool-handlers/enrichment.mjs').then(module => module.exploreGround),
};

function resultSummary(name, result) {
  if (!result?.ok) return null;
  const count = value => Array.isArray(value) ? value.length : 0;
  switch (name) {
    case 'ask_question': return { options: result.question?.options?.length || 0 };
    case 'set_trip_spec': return { days: result.days, startDate: result.startDate, requiredStays: result.requiredStays?.length || 0 };
    case 'resolve_origin': return { locationDetected: Boolean(result.locationDetected), originProvided: Boolean(result.originCity) };
    case 'discover_places': return { candidatePlaces: count(result.places), excludedVisited: result.excludedVisitedCount || 0 };
    case 'search_transport': return { outboundFlights: count(result.outboundFlights), returnFlights: count(result.returnFlights), outboundTrains: count(result.outboundTrains), returnTrains: count(result.returnTrains) };
    case 'search_stays': return { hotels: count(result.hotels) };
    case 'draft_plan': return { days: count(result.days), stops: Array.isArray(result.days) ? result.days.reduce((sum, day) => sum + count(day.places), 0) : 0, flightQuotes: result.flightQuotes || 0, trainQuotes: result.trainQuotes || 0, hotelQuotes: result.hotelQuotes || 0 };
    case 'search_attractions': return { products: count(result.products) };
    case 'search_dining': return { suggestions: count(result.suggestions) };
    case 'explore_ground': return { verifiedLegs: result.verifiedLegs || 0 };
    default: return null;
  }
}

function debugOutput(name, result) {
  if (!result?.ok) return { ok: false, code: result?.code || 'failed', message: result?.message || '工具执行失败' };
  const allowed = {
    ask_question: ['waitingForUser', 'question'],
    set_trip_spec: ['destination', 'originCity', 'days', 'startDate', 'endDate', 'totalBudgetCny', 'requiredStays', 'interests'],
    resolve_origin: ['originCity', 'locationDetected'],
    discover_places: ['places', 'excludedVisitedCount'],
    search_transport: ['sourcePriority', 'outboundFlights', 'returnFlights', 'outboundTrains', 'returnTrains'],
    search_stays: ['suggestedArea', 'hotels'],
    draft_plan: ['days', 'stayArea', 'flightQuotes', 'returnFlightQuotes', 'trainQuotes', 'returnTrainQuotes', 'hotelQuotes'],
    search_attractions: ['products'], search_dining: ['suggestions'], explore_ground: ['verifiedLegs', 'legs'],
  }[name] || [];
  return Object.fromEntries([['ok', true], ...allowed.filter(key => Object.hasOwn(result, key)).map(key => [key, result[key]])]);
}

export function debugInput(name, args) {
  if (!args || typeof args !== 'object') return {};
  if (name === 'set_trip_spec') return Object.fromEntries(['destination', 'originCity', 'days', 'startDate', 'totalBudgetCny', 'requiredStays', 'interests'].filter(key => Object.hasOwn(args, key)).map(key => [key, args[key]]));
  if (name === 'ask_question') return { question: String(args.question || '').slice(0, 240), options: Array.isArray(args.options) ? args.options.slice(0, 5).map(item => ({ id: item.id, label: item.label })) : [] };
  if (name === 'draft_plan') return { placeIds: Array.isArray(args.placeIds) ? args.placeIds.slice(0, 45) : [] };
  return {};
}

export function createToolExecutor(context) {
  const cache = context.cache || new Map();
  return async (name, args = {}, internal = false, turn = null) => {
    const started = Date.now();
    if (Date.now() >= context.deadline) return toolError('deadline', '规划超时');
    if (name !== 'draft_plan' && name !== 'set_trip_spec' && name !== 'ask_question' && cache.has(name)) {
      const cached = cache.get(name);
      context.onEvent?.({ type: 'tool_cache_hit', tool: name, turn, source: internal ? 'agent' : 'model', input: debugInput(name, args), output: debugOutput(name, cached), summary: resultSummary(name, cached) });
      return cached;
    }
    context.onEvent?.({ type: 'tool_start', tool: name, turn, source: internal ? 'agent' : 'model', input: debugInput(name, args) });
    let result;
    try {
      const handler = loaders[name] ? await loaders[name]() : null;
      result = handler ? await handler({ ...context, startDate: context.state.startDate || context.startDate, cache, internal }, args) : toolError('unknown_tool', '未知工具');
    } catch (error) {
      result = toolError('tool_failed', error.message || '工具执行失败');
      context.warnings.push(`${name} 执行失败`);
    }
    const entry = { tool: name, ok: result.ok === true, code: result.ok ? 'ok' : String(result.code || 'failed'), durationMs: Date.now() - started, summary: resultSummary(name, result) };
    context.trace.push(entry);
    context.onEvent?.({ type: 'tool_end', turn, source: internal ? 'agent' : 'model', output: debugOutput(name, result), ...entry });
    if (name === 'set_trip_spec' && result.ok) context.onEvent?.({ type: 'trip_memory_updated', turn, fields: debugInput(name, args), memory: debugOutput(name, result) });
    if (name !== 'draft_plan' && name !== 'set_trip_spec' && name !== 'ask_question' && (result.ok || result.code === 'no_new_places')) cache.set(name, result);
    return result;
  };
}
