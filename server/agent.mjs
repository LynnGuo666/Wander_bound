import { CITY_CATALOG } from '../shared/catalog.mjs';
import { parseTripRequest } from '../shared/planner.mjs';
import * as defaultProviders from './providers.mjs';
import { STEP_MODEL } from './step-client.mjs';
import { AGENT_TOOLS } from './agent/definitions.mjs';
import { runModelLoop } from './agent/model-loop.mjs';
import { buildCapabilityStatus, planInvariant } from './agent/plan-output.mjs';
import { cleanCity, nextFriday, safeMemory, validDate } from './agent/request.mjs';
import { createToolExecutor } from './agent/tools.mjs';

export { AGENT_TOOLS };

export async function runTravelAgent(input, {
  model = null, providers = defaultProviders, now = new Date(), maxDurationMs = 100000, onEvent = null,
} = {}) {
  const events = [];
  const emit = event => {
    const entry = { sequence: events.length + 1, at: new Date().toISOString(), ...event };
    events.push(entry);
    onEvent?.(entry);
  };
  const parsed = parseTripRequest(String(input.query || '').slice(0, 600));
  const explicitDestination = cleanCity(input.destination);
  const explicitDays = input.days == null || input.days === '' ? null : Number(input.days);
  const startDate = String(input.startDate || nextFriday(now));
  const memory = safeMemory(input.memory || {});
  const state = {
    destination: explicitDestination || cleanCity(parsed.destination),
    days: explicitDays ?? parsed.days ?? 3,
    desiredInterests: parsed.interests,
    originCity: cleanCity(input.originCity || memory.homeCity),
    locationDetected: false,
    places: [], flights: [], returnFlights: [], trains: [], returnTrains: [], hotels: [], plan: null,
    originDone: false, placesDone: false, availableCount: 0, transportDone: false, staysDone: false,
    attractionsDone: false, diningDone: false, groundDone: false,
    drafts: 0,
    providerStatus: providers.providerAvailability(),
  };
  emit({ type: 'run_start', model: STEP_MODEL, mode: model ? 'model' : 'deterministic' });
  if (!validDate(startDate) || (explicitDays !== null && (!Number.isInteger(explicitDays) || explicitDays < 1 || explicitDays > 7))) {
    return { status: 400, error: '请填写有效出发日期和 1–7 天的天数。' };
  }
  const deadline = Date.now() + maxDurationMs;
  const trace = [];
  const warnings = [];
  const execute = createToolExecutor({ input, state, providers, memory, startDate, explicitDestination, explicitDays, deadline, warnings, trace, onEvent: emit });
  const { mode, modelError, modelTurns, toolCalls, usage } = await runModelLoop({ model, input, state, memory, startDate, deadline, execute, warnings, onEvent: emit });

  if (!state.plan) {
    emit({ type: 'fallback_start', reason: model ? modelError || 'incomplete_plan' : 'model_unconfigured' });
    if (!state.destination || !Number.isInteger(state.days) || state.days < 1 || state.days > 7) {
      return { status: 400, error: '无法确定目的地或旅行天数。请明确输入城市与 1–7 天。', agentRun: { status: mode, model: STEP_MODEL, modelError, modelTurns, toolCalls, trace, warnings } };
    }
    for (const name of ['resolve_origin', 'discover_places', 'search_transport', 'search_stays']) {
      const result = await execute(name);
      if (result.code === 'no_new_places') return { status: 422, error: result.message, agentRun: { status: mode, model: STEP_MODEL, modelError, modelTurns, toolCalls, trace, warnings } };
      if (!result.ok) warnings.push(`${name} 未完成：${result.code}`);
    }
    const result = await execute('draft_plan', { placeIds: [] }, true);
    if (!result.ok) return { status: 422, error: result.message, agentRun: { status: mode, model: STEP_MODEL, modelError, modelTurns, toolCalls, trace, warnings } };
  }

  if (!state.attractionsDone) await execute('search_attractions', {}, true);
  if (!state.diningDone) await execute('search_dining', {}, true);
  if (!state.groundDone) await execute('explore_ground', {}, true);

  const allAvailable = [...(CITY_CATALOG[state.destination]?.places || []), ...state.places];
  const invalid = planInvariant(state.plan, memory, allAvailable);
  emit({ type: 'validation', ok: !invalid, code: invalid ? 'plan_invariant' : 'ok' });
  if (invalid) return { status: 422, error: invalid, agentRun: { status: 'degraded', model: STEP_MODEL, modelError, modelTurns, toolCalls, trace, warnings } };
  const enriched = state.plan;
  if (state.providerStatus.amap.configured && !state.providerStatus.amap.result) {
    state.providerStatus.amap.result = enriched.itinerary.some(day => day.stops.some(stop => stop.travelSource?.startsWith('高德'))) ? 'ok' : '本次未取到路线';
  }
  const capabilityStatus = buildCapabilityStatus(enriched, state);
  return {
    ...enriched,
    locationDetected: state.locationDetected,
    capabilityStatus,
    agentRun: { status: mode, model: STEP_MODEL, modelError, modelTurns, toolCalls, trace, events, warnings, usage },
  };
}
