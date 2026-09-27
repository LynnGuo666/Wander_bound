import { CITY_CATALOG } from '../shared/catalog.mjs';
import { parseTripRequest } from '../shared/planner.mjs';
import * as defaultProviders from './providers.mjs';
import { STEP_MODEL, stepChannel } from './step-client.mjs';
import { AGENT_TOOLS } from './agent/definitions.mjs';
import { runModelLoop } from './agent/model-loop.mjs';
import { buildCapabilityStatus, planInvariant } from './agent/plan-output.mjs';
import { cleanCity, nextFriday, safeMemory, validDate } from './agent/request.mjs';
import { createToolExecutor } from './agent/tools.mjs';

export { AGENT_TOOLS };

export async function runTravelAgent(input, {
  model = null, providers = defaultProviders, providerPriority = {}, now = new Date(), maxDurationMs = 300000, onEvent = null, signal = null, resume = null,
} = {}) {
  const events = resume?.events || [];
  const emit = event => {
    const entry = { sequence: events.length + 1, at: new Date().toISOString(), ...event };
    events.push(entry);
    onEvent?.(entry);
  };
  const channel = model?.channel || stepChannel();
  const parsed = model ? null : parseTripRequest(String(input.query || '').slice(0, 600));
  const explicitDestination = cleanCity(input.destination);
  const explicitDays = input.days == null || input.days === '' ? null : Number(input.days);
  const startDate = String(input.startDate || nextFriday(now));
  const memory = resume?.memory || safeMemory(input.memory || {});
  const state = resume?.state || {
    destination: explicitDestination || (model ? '' : cleanCity(parsed.destination)),
    days: explicitDays ?? (model ? null : parsed.days ?? 3),
    startDate,
    totalBudgetCny: null,
    requiredStays: [],
    pendingQuestion: null,
    desiredInterests: model ? [] : parsed.interests,
    originCity: cleanCity(input.originCity || memory.homeCity),
    locationDetected: false,
    places: [], flights: [], returnFlights: [], trains: [], returnTrains: [], hotels: [], plan: null,
    originDone: false, placesDone: false, availableCount: 0, transportDone: false, staysDone: false,
    attractionsDone: false, diningDone: false, groundDone: false,
    drafts: 0,
    providerStatus: providers.providerAvailability(),
  };
  if (resume) {
    state.pendingQuestion = null;
    state.answerNeedsCommit = true;
    emit({ type: 'user_answer', questionId: resume.answer.questionId, question: resume.answer.question, answer: resume.answer.value });
  } else emit({ type: 'run_start', model: STEP_MODEL, channel, mode: model ? 'model' : 'deterministic' });
  if (!validDate(startDate) || (explicitDays !== null && (!Number.isInteger(explicitDays) || explicitDays < 1 || explicitDays > 21))) {
    return { status: 400, error: '请填写有效出发日期和 1–21 天的天数。' };
  }
  const deadline = Date.now() + maxDurationMs;
  const trace = resume?.trace || [];
  const warnings = resume?.warnings || [];
  const cache = resume?.cache || new Map();
  const execute = createToolExecutor({ input, state, providers, providerPriority, memory, startDate, explicitDestination, explicitDays, deadline, warnings, trace, cache, onEvent: emit });
  const { mode, modelError, modelTurns, toolCalls, usage, messages } = await runModelLoop({ model, input, state, memory, startDate, deadline, execute, warnings, onEvent: emit, signal, resume });

  if (state.pendingQuestion) return { status: 409, needsInput: true, question: state.pendingQuestion,
    agentRun: { status: 'waiting_for_user', model: STEP_MODEL, channel, modelTurns, toolCalls, trace, events, warnings, usage },
    continuation: { state, memory, trace, events, warnings, cache, messages, modelTurns, toolCalls, usage } };

  if (!state.plan) {
    if (model) {
      emit({ type: 'run_failed', reason: modelError || 'incomplete_plan' });
      return { status: 502, error: modelError ? `Step 未完成规划（${modelError}）。请查看完整调试记录。` : 'Step 没有提交完整行程。请查看完整调试记录。',
        agentRun: { status: mode, model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, events, warnings, usage } };
    }
    emit({ type: 'fallback_start', reason: model ? modelError || 'incomplete_plan' : 'model_unconfigured' });
    if (!state.destination || !Number.isInteger(state.days) || state.days < 1 || state.days > 21) {
      return { status: 400, error: '无法确定目的地或旅行天数。请明确输入城市与 1–21 天。', agentRun: { status: mode, model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, warnings } };
    }
    for (const name of ['resolve_origin', 'discover_places', 'search_transport', 'search_stays']) {
      const result = await execute(name);
      if (result.code === 'no_new_places') return { status: 422, error: result.message, agentRun: { status: mode, model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, warnings } };
      if (!result.ok) warnings.push(`${name} 未完成：${result.code}`);
    }
    const result = await execute('draft_plan', { placeIds: [] }, true);
    if (!result.ok) return { status: 422, error: result.message, agentRun: { status: mode, model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, warnings } };
  }

  if (!state.attractionsDone) await execute('search_attractions', {}, true);
  if (!state.diningDone) await execute('search_dining', {}, true);
  if (!state.groundDone) await execute('explore_ground', {}, true);

  const allAvailable = [...(CITY_CATALOG[state.destination]?.places || []), ...state.places];
  const invalid = planInvariant(state.plan, memory, allAvailable);
  emit({ type: 'validation', ok: !invalid, code: invalid ? 'plan_invariant' : 'ok' });
  if (invalid) return { status: 422, error: invalid, agentRun: { status: 'degraded', model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, warnings } };
  const enriched = state.plan;
  const chosenProvider = (offers, id, order) => {
    const source = offers.find(item => item.id === id)?.sourceId || null;
    return { preferred: order?.[0] || null, selected: source, fallback: Boolean(source && order?.length && source !== order[0]) };
  };
  enriched.sourceSelection = {
    outboundFlight: chosenProvider(enriched.flights, enriched.recommendedOutboundFlightId, providerPriority.flights),
    returnFlight: chosenProvider(enriched.returnFlights, enriched.recommendedReturnFlightId, providerPriority.flights),
    outboundTrain: chosenProvider(enriched.trains, enriched.recommendedOutboundTrainId, providerPriority.trains),
    returnTrain: chosenProvider(enriched.returnTrains, enriched.recommendedReturnTrainId, providerPriority.trains),
  };
  if (state.providerStatus.amap.configured && !state.providerStatus.amap.result) {
    state.providerStatus.amap.result = enriched.itinerary.some(day => day.stops.some(stop => stop.travelSource?.startsWith('高德'))) ? 'ok' : '本次未取到路线';
  }
  const capabilityStatus = buildCapabilityStatus(enriched, state);
  enriched.requiredStays = state.requiredStays;
  enriched.totalBudgetCny = state.totalBudgetCny;
  enriched.startDate = state.startDate;
  enriched.endDate = state.plan.endDate;
  if (state.totalBudgetCny !== null) {
    const chosen = enriched.selectedTransportMode === 'train'
      ? [[...enriched.trains, ...enriched.returnTrains], [enriched.recommendedOutboundTrainId, enriched.recommendedReturnTrainId]]
      : [[...enriched.flights, ...enriched.returnFlights], [enriched.recommendedOutboundFlightId, enriched.recommendedReturnFlightId]];
    const selectedQuotes = chosen[1].map(id => chosen[0].find(item => item.id === id));
    const knownTransportCostCny = selectedQuotes.filter(item => Number.isFinite(item?.totalPrice)).reduce((sum, item) => sum + item.totalPrice, 0);
    enriched.budgetAssessment = { totalBudgetCny: state.totalBudgetCny, knownTransportCostCny,
      remainingAfterKnownTransportCny: state.totalBudgetCny - knownTransportCostCny,
      quotedLegs: selectedQuotes.filter(item => Number.isFinite(item?.totalPrice)).length,
      status: knownTransportCostCny > state.totalBudgetCny ? 'known_transport_exceeds_budget' : 'partial_cost_only' };
  }
  emit({ type: 'result_assembled', output: {
    selectionMethod: mode === 'completed' ? '模型提交已查询的地点 ID；服务端排程与校验' : '服务端按兴趣、距离与已到访记录筛选地点',
    days: enriched.itinerary.length,
    stops: enriched.itinerary.reduce((sum, day) => sum + day.stops.length, 0),
    itinerary: enriched.itinerary.map(day => ({ day: day.day, date: day.date, stops: day.stops.map(stop => ({ id: stop.id, name: stop.name, start: stop.start, travelSource: stop.travelSource })) })),
    selectedTransportMode: enriched.selectedTransportMode,
    recommendedOutboundFlightId: enriched.recommendedOutboundFlightId,
    recommendedOutboundTrainId: enriched.recommendedOutboundTrainId,
    recommendedReturnFlightId: enriched.recommendedReturnFlightId,
    recommendedReturnTrainId: enriched.recommendedReturnTrainId,
    sourceSelection: enriched.sourceSelection,
    flights: enriched.flights.length + enriched.returnFlights.length,
    trains: enriched.trains.length + enriched.returnTrains.length,
    hotels: enriched.hotels.length,
    attractionProducts: enriched.attractionOffers?.length || 0,
    diningSuggestions: enriched.dining.length,
    verifiedGroundLegs: enriched.groundJourneys.length,
    capabilities: Object.fromEntries(Object.entries(capabilityStatus).map(([key, value]) => [key, { status: value.status, source: value.source }])),
    calculation: '已核实地点 ID → 按兴趣与距离分配到每天、估算转场时间 → 根据价格、红眼和到达时间排序交通 → 按价格、品牌与距离排序酒店 → 叠加供应商结果 → 校验地点唯一性、到访记录和时间约束',
  } });
  return {
    ...enriched,
    locationDetected: state.locationDetected,
    capabilityStatus,
    agentRun: { status: mode, model: STEP_MODEL, channel, modelError, modelTurns, toolCalls, trace, events, warnings, usage },
  };
}
