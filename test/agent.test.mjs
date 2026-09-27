import test from 'node:test';
import assert from 'node:assert/strict';
import { runTravelAgent } from '../server/agent.mjs';
import { createStepClient, STEP_BASE_URL, STEP_MODEL, stepChannel } from '../server/step-client.mjs';

// 夹具模拟高德 POI 的真实形状：地点来自供应商查询，没有编造的游玩时长。
const FIXTURE_PLACES = [
  { id: 'sz-nantou', name: '南头古城', lat: 22.5345, lng: 113.9233, area: '南山', category: '历史街区', duration: null },
  { id: 'sz-oct', name: '华侨城创意文化园', lat: 22.5428, lng: 113.9864, area: '南山', category: '艺术', duration: null },
  { id: 'sz-bay', name: '深圳湾公园', lat: 22.5160, lng: 113.9440, area: '南山', category: '海岸', duration: null },
  { id: 'sz-seaworld', name: '海上世界', lat: 22.4848, lng: 113.9182, area: '蛇口', category: '街区', duration: null },
  { id: 'sz-museum', name: '深圳博物馆', lat: 22.5458, lng: 114.0606, area: '福田', category: '博物馆', duration: null },
  { id: 'sz-lianhuashan', name: '莲花山公园', lat: 22.5560, lng: 114.0614, area: '福田', category: '公园', duration: null },
  { id: 'sz-huaqiangbei', name: '华强北', lat: 22.5457, lng: 114.0885, area: '福田', category: '城市探索', duration: null },
  { id: 'sz-baoanbay', name: '欢乐港湾', lat: 22.5527, lng: 113.8794, area: '宝安', category: '海岸', duration: null },
  { id: 'sz-dafen', name: '大芬油画村', lat: 22.6142, lng: 114.1362, area: '龙岗', category: '艺术', duration: null },
  { id: 'sz-gankeng', name: '甘坑古镇', lat: 22.6302, lng: 114.0906, area: '龙岗', category: '历史街区', duration: null },
];

const request = { query: '从上海去深圳玩三天，便宜白天航班，别重复去过的地方', destination: '深圳', days: 3, originCity: '上海', startDate: '2026-10-09', memory: {
  visitedCities: ['深圳'], visitedPlaces: [{ id: 'sz-oct', name: '华侨城创意文化园', city: '深圳' }],
} };

function stubProviders(overrides = {}) {
  return {
    providerAvailability: () => ({
      amap: { configured: true, label: '高德' }, dida: { configured: false, label: '道旅' }, duffel: { configured: false, label: 'Duffel' },
    }),
    reverseLocation: async () => null,
    searchAmapPlaces: async city => city === '深圳' ? FIXTURE_PLACES : [],
    searchDuffelFlights: async () => [],
    searchDidaHotels: async () => [],
    searchAmapDining: async () => [],
    enrichRoutes: async plan => plan,
    ...overrides,
  };
}

const call = (name, args = {}, id = name) => ({ id, type: 'function', function: { name, arguments: JSON.stringify(args) } });
const tools = (...toolCalls) => ({ message: { role: 'assistant', content: null, tool_calls: toolCalls }, finishReason: 'tool_calls', usage: { prompt_tokens: 100, completion_tokens: 30 } });
const final = { message: { role: 'assistant', content: '行程已完成。' }, finishReason: 'stop', usage: { prompt_tokens: 50, completion_tokens: 10 } };

test('Step 5 agent runs tools, rejects an invented place, then validates a corrected draft', async () => {
  const selected = ['sz-nantou', 'sz-baoanbay', 'sz-gankeng', 'sz-dafen', 'sz-huaqiangbei', 'sz-lianhuashan', 'sz-museum'];
  const script = [
    tools(call('set_trip_spec', { destination: '深圳', days: 3 }), call('resolve_origin'), call('discover_places')),
    tools(call('search_transport'), call('search_stays')),
    tools(call('draft_plan', { placeIds: [...selected.slice(0, 6), 'made-up-place'] }, 'bad-draft')),
    tools(call('draft_plan', { placeIds: selected }, 'good-draft')),
    final,
  ];
  let calls = 0;
  let transcript = '';
  const toolLists = [];
  const model = { complete: async (messages, advertised) => {
    transcript = JSON.stringify(messages);
    toolLists.push(advertised.map(tool => tool.function.name));
    return script[calls++];
  } };
  const plan = await runTravelAgent(request, { model, providers: stubProviders() });
  assert.equal(plan.agentRun.status, 'completed');
  assert.equal(plan.agentRun.model, STEP_MODEL);
  assert.equal(plan.agentRun.modelTurns, 5);
  assert.equal(plan.agentRun.toolCalls, 7);
  assert.deepEqual(toolLists, [
    ['ask_question', 'set_trip_spec', 'discover_places', 'resolve_origin'],
    ['ask_question', 'search_transport', 'search_stays'],
    ['ask_question', 'draft_plan'],
    ['ask_question', 'draft_plan'],
    ['search_attractions', 'search_dining', 'explore_ground'],
  ]);
  assert.equal(plan.agentRun.trace.filter(item => item.tool === 'draft_plan').length, 2);
  assert.equal(plan.agentRun.trace.find(item => item.tool === 'draft_plan').ok, false);
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => selected.includes(stop.id)));
  assert.ok(plan.itinerary.flatMap(day => day.stops).every(stop => stop.id !== 'sz-oct'));
  assert.deepEqual(plan.flights, []);
  assert.ok(!transcript.includes('华侨城创意文化园'));
  const events = plan.agentRun.events;
  assert.equal(events.filter(event => event.type === 'model_turn_end').length, 5);
  assert.equal(events.filter(event => event.type === 'model_turn_end').reduce((sum, event) => sum + event.usage.prompt_tokens, 0), plan.agentRun.usage.prompt_tokens);
  assert.ok(events.some(event => event.type === 'tool_start' && event.tool === 'draft_plan' && event.input.placeIds.includes('made-up-place')));
  assert.ok(events.some(event => event.type === 'tool_end' && event.tool === 'draft_plan' && event.output.code === 'unverified_place'));
  assert.ok(events.some(event => event.type === 'result_assembled' && event.output.stops > 0 && event.output.capabilities.attractions.source));
});

test('early model answer triggers one reminder, then reports an incomplete model run', async () => {
  let calls = 0;
  const model = { complete: async () => { calls += 1; return final; } };
  const plan = await runTravelAgent(request, { model, providers: stubProviders() });
  assert.equal(calls, 2);
  assert.equal(plan.agentRun.status, 'degraded');
  assert.equal(plan.status, 502);
  assert.ok(plan.agentRun.events.some(event => event.type === 'run_failed'));
});

test('Step 5 receives the complete natural-language request and can pause for a choice with Other', async () => {
  const query = '我希望10月2号到10月5号一定在柳州，长春出发，放假13天，总预算4000元';
  const model = { backend: 'external-stepfun', complete: async (messages, available) => {
    assert.ok(JSON.stringify(messages).includes(query));
    assert.ok(available.some(tool => tool.function.name === 'ask_question'));
    return tools(call('ask_question', { question: '剩余假期如何安排？', options: [
      { id: 'liuzhou', label: '都在柳州' }, { id: 'nearby', label: '顺路游览其他城市' },
    ] }));
  } };
  const result = await runTravelAgent({ query }, { model, providers: stubProviders() });
  assert.equal(result.status, 409);
  assert.equal(result.needsInput, true);
  assert.equal(result.agentRun.status, 'waiting_for_user');
  assert.deepEqual(result.question.options.map(option => option.id), ['liuzhou', 'nearby', 'other']);
});

test('answers continue one loop and commit each answer before the next question', async () => {
  const seen = [];
  const script = [
    tools(call('ask_question', { question: '从哪个城市出发？', options: [{ id: 'cc', label: '长春' }, { id: 'sh', label: '上海' }] }, 'q-city')),
    tools(call('set_trip_spec', { originCity: '长春' }, 'save-city')),
    tools(call('ask_question', { question: '哪天出发？', options: [{ id: 'd1', label: '2026-09-30' }, { id: 'd2', label: '2026-10-01' }] }, 'q-date')),
    tools(call('set_trip_spec', { startDate: '2026-09-30' }, 'save-date')),
    tools(call('ask_question', { question: '总共旅行几天？', options: [{ id: 'n13', label: '13 天' }, { id: 'n7', label: '7 天' }] }, 'q-days')),
  ];
  const model = { complete: async (messages, available) => {
    seen.push({ messages: structuredClone(messages), tools: available.map(tool => tool.function.name) });
    return script[seen.length - 1];
  } };
  const input = { query: '帮我规划旅行' };
  const first = await runTravelAgent(input, { model, providers: stubProviders() });
  assert.equal(first.status, 409);
  assert.equal(first.agentRun.modelTurns, 1);
  const second = await runTravelAgent(input, { model, providers: stubProviders(), resume: {
    ...first.continuation,
    answer: { questionId: first.question.id, question: first.question.question, value: '长春' },
  } });
  assert.equal(second.status, 409);
  assert.equal(second.agentRun.modelTurns, 3);
  assert.equal(second.agentRun.toolCalls, 3);
  assert.equal(second.continuation.state.originCity, '长春');
  assert.deepEqual(seen[1].tools, ['set_trip_spec']);
  assert.ok(JSON.stringify(seen[1].messages).includes('从哪个城市出发？'));
  assert.ok(seen[2].messages.some(message => message.role === 'tool' && message.content.includes('"originCity":"长春"')));
  const third = await runTravelAgent(input, { model, providers: stubProviders(), resume: {
    ...second.continuation,
    answer: { questionId: second.question.id, question: second.question.question, value: '2026-09-30' },
  } });
  assert.equal(third.status, 409);
  assert.equal(third.agentRun.modelTurns, 5);
  assert.equal(third.continuation.state.originCity, '长春');
  assert.equal(third.continuation.state.startDate, '2026-09-30');
  assert.deepEqual(seen[3].tools, ['set_trip_spec']);
  assert.deepEqual(third.agentRun.events.filter(event => event.type === 'trip_memory_updated').map(event => Object.keys(event.fields)), [['originCity'], ['startDate']]);
  assert.deepEqual(third.agentRun.events.map(event => event.sequence), third.agentRun.events.map((_, index) => index + 1));
});

test('Step 5 structured 13-day stay preserves fixed dates and budget without invented places', async () => {
  const script = [
    tools(call('set_trip_spec', { destination: '柳州', originCity: '长春', days: 13, startDate: '2026-09-30', totalBudgetCny: 4000,
      requiredStays: [{ city: '柳州', from: '2026-10-02', to: '2026-10-05' }] }), call('resolve_origin'), call('discover_places')),
    tools(call('search_transport'), call('search_stays')),
    tools(call('draft_plan', { placeIds: [] })), final,
  ];
  let turn = 0;
  const model = { backend: 'external-stepfun', complete: async () => script[turn++] };
  const plan = await runTravelAgent({ query: '10月2日到5日一定在柳州，长春出发，放假13天，预算4000元',
    answer: { optionId: 'liuzhou', label: '都在柳州' } }, { model, providers: stubProviders() });
  assert.equal(plan.agentRun.status, 'completed');
  assert.equal(plan.startDate, '2026-09-30');
  assert.equal(plan.days, 13);
  assert.equal(plan.totalBudgetCny, 4000);
  assert.equal(plan.itinerary.filter(day => day.requiredStay).length, 4);
  assert.equal(plan.itinerary.flatMap(day => day.stops).length, 0);
});

test('an empty model draft is not reported as model-completed planning', async () => {
  let turn = 0;
  const script = [
    tools(call('set_trip_spec', { destination: '深圳', days: 3 }), call('resolve_origin'), call('discover_places')),
    tools(call('search_transport'), call('search_stays')),
    tools(call('draft_plan', { placeIds: [] })),
    final,
  ];
  const model = { complete: async () => script[turn++] };
  const plan = await runTravelAgent(request, { model, providers: stubProviders() });
  assert.equal(plan.agentRun.status, 'degraded');
  assert.ok(plan.agentRun.trace.some(item => item.tool === 'draft_plan' && !item.ok));
  assert.equal(plan.status, 502);
});

test('a tool that has not been exposed cannot run ahead of its stage', async () => {
  let turn = 0;
  const model = { complete: async (messages, advertised) => {
    turn += 1;
    if (turn === 1) {
      assert.ok(!advertised.some(tool => tool.function.name === 'search_transport'));
      return tools(call('search_transport', {}, 'early-transport'));
    }
    const response = messages.find(message => message.role === 'tool' && message.tool_call_id === 'early-transport');
    assert.equal(JSON.parse(response.content).code, 'tool_not_loaded');
    return final;
  } };
  const progress = [];
  const plan = await runTravelAgent(request, { model, providers: stubProviders(), onEvent: event => progress.push(event) });
  assert.equal(plan.agentRun.status, 'degraded');
  assert.equal(plan.agentRun.trace.filter(item => item.tool === 'search_transport').length, 0);
  assert.ok(progress.some(event => event.type === 'tool_rejected' && event.tool === 'search_transport' && event.output.code === 'tool_not_loaded'));
});

test('model outage reports a debuggable error without inventing supplier offers', async () => {
  const model = { complete: async () => { const error = new Error('timeout'); error.code = 'deadline'; throw error; } };
  const plan = await runTravelAgent(request, { model, providers: stubProviders() });
  assert.equal(plan.agentRun.status, 'degraded');
  assert.equal(plan.agentRun.modelError, 'deadline');
  assert.equal(plan.status, 502);
  assert.ok(plan.agentRun.events.some(event => event.type === 'model_error' && event.code === 'deadline'));
});

test('a city without place data keeps a dated itinerary without inventing POIs', async () => {
  let supplierCalls = 0;
  const providers = stubProviders({
    searchDuffelFlights: async () => { supplierCalls += 1; return []; },
    searchDidaHotels: async () => { supplierCalls += 1; return []; },
  });
  const result = await runTravelAgent({ query: '去苏州玩三天', destination: '苏州', days: 3, startDate: '2026-10-09' }, { providers });
  assert.equal(result.destination, '苏州');
  assert.equal(result.itinerary.length, 3);
  assert.equal(result.itinerary.flatMap(day => day.stops).length, 0);
  assert.equal(supplierCalls, 0);
});

test('repeated model tool calls are bounded and later rejected after the stage closes', async () => {
  let modelCalls = 0;
  let locationCalls = 0;
  const model = { complete: async () => { modelCalls += 1; return tools(call('resolve_origin', {}, `location-${modelCalls}`)); } };
  const providers = stubProviders({
    providerAvailability: () => ({ amap: { configured: true, label: '高德' }, dida: { configured: false, label: '道旅' }, duffel: { configured: false, label: 'Duffel' } }),
    reverseLocation: async () => { locationCalls += 1; return '上海'; },
  });
  const plan = await runTravelAgent({ ...request, originCity: '', location: { lat: 31.2, lng: 121.5 } }, { model, providers });
  assert.equal(modelCalls, 200);
  assert.equal(locationCalls, 1);
  assert.equal(plan.agentRun.status, 'degraded');
  assert.equal(plan.status, 502);
  assert.ok(plan.agentRun.events.some(event => event.type === 'tool_rejected' && event.tool === 'resolve_origin' && event.code === 'tool_not_loaded'));
});

test('malformed supplier data is discarded before it reaches clients', async () => {
  const providers = stubProviders({
    searchDuffelFlights: async () => [{ id: 'bad', totalPrice: null, departureAt: '', arrivalAt: '', currency: 'CNY' }],
    searchDidaHotels: async () => [{ id: 'bad', currency: 'CNY' }],
  });
  const plan = await runTravelAgent(request, { providers });
  assert.deepEqual(plan.flights, []);
  assert.deepEqual(plan.hotels, []);
});

test('agent merges read-only OTA flights, trains and selected attraction products with provenance', async () => {
  const providers = stubProviders({
    providerAvailability: () => ({
      amap: { configured: true, label: '高德' }, dida: { configured: false, label: '道旅' }, duffel: { configured: false, label: 'Duffel' },
      flyai: { configured: true, label: '飞猪 FlyAI' }, tuniu: { configured: true, label: '途牛 MCP' },
    }),
    searchFlyaiTransport: async (kind, origin, destination, date) => [{
      id: `flyai-${kind}-${origin}-${date}`, provider: '飞猪 FlyAI', departureAt: `${date}T09:00:00`, arrivalAt: `${date}T11:00:00`,
      totalPrice: kind === 'flight' ? 500 : 260, currency: 'CNY', stops: 0,
    }],
    searchTuniuTransport: async (kind, origin, destination, date) => kind === 'flight' ? [{
      id: `tuniu-${origin}-${date}`, provider: '途牛 MCP', departureAt: `${date}T08:00:00`, arrivalAt: `${date}T10:00:00`,
      totalPrice: 450, currency: 'CNY', stops: 0,
    }] : [],
    searchAttractionProducts: async (_city, places) => [{ placeId: places[0].id, name: places[0].name, provider: '飞猪 FlyAI',
      productName: '成人票', price: null, currency: null, bookingUrl: 'https://example.com/ticket' }],
  });
  const plan = await runTravelAgent(request, { providers });
  assert.equal(plan.flights.length, 2);
  assert.equal(plan.trains.length, 1);
  assert.equal(plan.flights[0].provider, '途牛 MCP');
  assert.equal(plan.recommendedOutboundFlightId, plan.flights[0].id);
  assert.equal(plan.attractionOffers[0].price, null);
  assert.equal(plan.capabilityStatus.attractions.status, 'products_found');
  assert.equal(plan.capabilityStatus.reviews.status, 'unavailable');
  assert.ok(plan.agentRun.trace.some(item => item.tool === 'search_attractions'));
});

test('a partial OTA outage keeps successful schedules and reports a partial failure', async () => {
  const providers = stubProviders({
    providerAvailability: () => ({ amap: { configured: false, label: '高德' }, dida: { configured: false, label: '道旅' },
      duffel: { configured: false, label: 'Duffel' }, flyai: { configured: true, label: '飞猪 FlyAI' } }),
    searchFlyaiTransport: async (kind, origin, destination, date) => {
      if (kind === 'train' && origin === '上海') throw new Error('upstream busy');
      return [{ id: `${kind}-${origin}`, provider: '飞猪 FlyAI', departureAt: `${date}T08:00:00`, arrivalAt: `${date}T10:00:00`,
        totalPrice: kind === 'train' ? null : 400, currency: kind === 'train' ? null : 'CNY', stops: 0 }];
    },
  });
  const plan = await runTravelAgent(request, { providers });
  assert.equal(plan.flights.length, 1);
  assert.equal(plan.returnTrains.length, 1);
  assert.equal(plan.providerStatus.flyai.partialError, true);
  assert.equal(plan.providerStatus.flyai.error, false);
  assert.equal(plan.capabilityStatus.trains.status, 'schedules_found');
});

test('dining stays grounded in nearby supplier POIs and excludes visited restaurants', async () => {
  const providers = stubProviders({
    searchAmapDining: async (_city, anchors) => anchors.flatMap(anchor => [
      { id: `visited-${anchor.day}`, name: '吃过的店', day: anchor.day, lat: anchor.lat, lng: anchor.lng, source: '高德餐饮 POI' },
      { id: `food-${anchor.day}`, name: `第${anchor.day}天餐厅`, day: anchor.day, lat: anchor.lat, lng: anchor.lng,
        rating: 4.5, averageCost: 90, currency: 'CNY', source: '高德餐饮 POI' },
      { id: `far-${anchor.day}`, name: '远处餐厅', day: anchor.day, lat: 0, lng: 0, source: '高德餐饮 POI' },
    ]),
  });
  const plan = await runTravelAgent({ ...request, memory: { ...request.memory, visitedPlaces: [
    ...request.memory.visitedPlaces, ...[1, 2, 3].map(day => ({ id: `visited-${day}`, name: '吃过的店', city: '深圳' })),
  ] } }, { providers });
  assert.equal(plan.dining.length, 3);
  assert.ok(plan.dining.every(item => item.id.startsWith('food-') && item.source === '高德餐饮 POI'));
  assert.ok(plan.itinerary.every(day => day.diningSuggestions.length === 1));
  assert.equal(plan.providerStatus.dining.result, 'ok');
});

test('dining ranking considers rating and per-person budget as well as distance', async () => {
  const providers = stubProviders({ searchAmapDining: async (_city, anchors) => anchors.flatMap(anchor => [
    { id: `close-${anchor.day}`, name: '就近普通店', day: anchor.day, lat: anchor.lat, lng: anchor.lng,
      rating: 3.5, averageCost: 70, source: '高德餐饮 POI' },
    { id: `better-${anchor.day}`, name: '稍远好评店', day: anchor.day, lat: anchor.lat + 0.004, lng: anchor.lng,
      rating: 4.6, averageCost: 85, source: '高德餐饮 POI' },
    { id: `expensive-${anchor.day}`, name: '高价店', day: anchor.day, lat: anchor.lat, lng: anchor.lng,
      rating: 4.8, averageCost: 600, source: '高德餐饮 POI' },
  ]) });
  const plan = await runTravelAgent({ ...request, memory: { ...request.memory, diningBudgetPerPerson: 100 } }, { providers });
  assert.ok(plan.dining.every(item => item.id.startsWith('better-')));
});

test('ground route detail is preserved with its source and imagery coverage is not fabricated', async () => {
  const providers = stubProviders({ enrichRoutes: async plan => ({ ...plan, groundJourneys: [{
    day: 1, from: '机场', to: plan.itinerary[0].stops[0].name, minutes: 42, mode: 'transit',
    source: '高德公共交通', walkingMeters: 350, segments: [{ mode: 'transit', line: '地铁11号线', board: '机场', alight: '前海湾' }],
    imagery: { status: 'check-on-device', provider: 'Apple MapKit Look Around' },
  }] }) });
  const plan = await runTravelAgent(request, { providers });
  assert.equal(plan.groundJourneys.length, 1);
  assert.equal(plan.groundJourneys[0].segments[0].board, '机场');
  assert.equal(plan.groundJourneys[0].imagery.status, 'check-on-device');
  assert.equal(plan.providerStatus.ground.result, 'ok');
});

test('a route provider cannot turn a valid day into an overnight itinerary', async () => {
  const providers = stubProviders({
    enrichRoutes: async plan => ({ ...plan, itinerary: plan.itinerary.map((day, index) => index === 0
      ? { ...day, stops: day.stops.map((stop, stopIndex) => stopIndex === 0 ? { ...stop, start: '23:30' } : stop) }
      : day) }),
  });
  const plan = await runTravelAgent(request, { providers });
  assert.notEqual(plan.itinerary[0].stops[0].start, '23:30');
  assert.ok(plan.agentRun.warnings.some(warning => warning.includes('时刻冲突')));
});

test('fully visited city does not claim to offer a new itinerary', async () => {
  const visitedPlaces = FIXTURE_PLACES.map(place => ({ id: place.id, name: place.name, city: '深圳' }));
  const result = await runTravelAgent({ ...request, memory: { ...request.memory, visitedPlaces } }, { providers: stubProviders() });
  assert.equal(result.status, 422);
  assert.match(result.error, /没有可核实/);
});

test('one through seven days keep unique verified stops without fabricated clock times', async () => {
  for (let days = 1; days <= 7; days += 1) {
    const plan = await runTravelAgent({ ...request, days }, { providers: stubProviders() });
    assert.equal(plan.itinerary.length, days);
    const stops = plan.itinerary.flatMap(day => day.stops);
    assert.equal(stops.length, new Set(stops.map(stop => stop.id)).size);
    assert.ok(stops.every(stop => stop.start === null && stop.travelSource === null));
    assert.ok(stops.every(stop => stop.id !== 'sz-oct'));
    assert.ok(plan.itinerary.every(day => day.stops.length > 0));
  }
});

test('Step client retries a rate limit and uses the exact Step 5 model ID', async () => {
  const bodies = [];
  const endpoints = [];
  let attempts = 0;
  const fetchImpl = async (url, requestOptions) => {
    endpoints.push(url);
    bodies.push(JSON.parse(requestOptions.body));
    attempts += 1;
    if (attempts === 1) return { ok: false, status: 429, headers: { get: () => '0' } };
    return { ok: true, json: async () => ({ choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: '完成' } }], usage: { prompt_tokens: 1, completion_tokens: 1 } }) };
  };
  const client = createStepClient({ apiKey: 'test-only', baseUrl: STEP_BASE_URL, fetchImpl, sleep: async () => {} });
  const response = await client.complete([{ role: 'user', content: 'hi' }], [], { deadline: Date.now() + 3000 });
  assert.equal(attempts, 2);
  assert.ok(bodies.every(body => body.model === 'step-5-preview'));
  assert.ok(bodies.every(body => body.stream === true));
  assert.ok(endpoints.every(url => url === 'https://api.stepfun.com/step_plan/v1/chat/completions'));
  assert.equal(client.channel, 'step-plan');
  assert.equal(stepChannel(STEP_BASE_URL), 'step-plan');
  assert.equal(response.message.content, '完成');
});

test('Step client assembles streamed public text, tool calls and token usage', async () => {
  const encoder = new TextEncoder();
  const chunks = [
    'data: {"choices":[{"delta":{"content":"<thi","reasoning_content":"另一段思考"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"nk>原始推"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"理</thi"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"nk>我先查"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"一下交通。","tool_calls":[{"index":0,"id":"call_1","function":{"name":"search_","arguments":"{"}}]}}]}\n\n',
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"transport","arguments":"}"}}]},"finish_reason":"tool_calls"}]}\n\n',
    'data: {"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":8}}\n\n',
    'data: [DONE]\n\n',
  ];
  const observed = [];
  const reasoning = [];
  const client = createStepClient({ apiKey: 'test-only', fetchImpl: async (_url, options) => {
    assert.equal(JSON.parse(options.body).stream, true);
    return { ok: true, headers: { get: () => 'text/event-stream' }, body: new ReadableStream({ start(controller) {
      const bytes = encoder.encode(chunks.join(''));
      for (let offset = 0; offset < bytes.length; offset += 7) controller.enqueue(bytes.slice(offset, offset + 7));
      controller.close();
    } }) };
  } });
  const result = await client.complete([], [], { onDelta: text => observed.push(text), onReasoning: text => reasoning.push(text) });
  assert.equal(result.message.content, '<think>原始推理</think>我先查一下交通。');
  assert.equal(result.message.tool_calls[0].function.name, 'search_transport');
  assert.equal(result.message.tool_calls[0].function.arguments, '{}');
  assert.equal(result.usage.prompt_tokens, 20);
  assert.equal(observed.join(''), '我先查一下交通。');
  assert.equal(reasoning.join(''), '另一段思考原始推理');
});

test('Step content-only analysis is streamed as thinking and reports output truncation', async () => {
  const frames = [
    'data: {"choices":[{"delta":{"content":"Let me analyze the user request. "}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"I should call a tool now."},"finish_reason":"length"}]}\n\n',
    'data: [DONE]\n\n',
  ].join('');
  const visible = [], thinking = [];
  const client = createStepClient({ apiKey: 'test-only', fetchImpl: async () => ({ ok: true,
    headers: { get: () => 'text/event-stream' }, body: new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode(frames)); controller.close();
    } }) }) });
  await assert.rejects(client.complete([], [], { onDelta: text => visible.push(text), onReasoning: text => thinking.push(text) }), error => error.code === 'output_limit');
  assert.deepEqual(visible, []);
  assert.equal(thinking.join(''), 'Let me analyze the user request. I should call a tool now.');
});

test('agent forwards model reasoning deltas without adding them to the public note', async () => {
  const events = [];
  const model = { complete: async (_messages, _tools, { onReasoning, onDelta }) => {
    onReasoning('原始片段一');
    onReasoning('原始片段二');
    onDelta('公开行动');
    return tools(call('ask_question', { question: '选哪种交通？', options: [
      { id: 'train', label: '火车' }, { id: 'plane', label: '飞机' },
    ] }));
  } };
  await runTravelAgent(request, { model, providers: stubProviders(), onEvent: event => events.push(event) });
  assert.equal(events.filter(event => event.type === 'model_reasoning_delta').map(event => event.text).join(''), '原始片段一原始片段二');
  assert.equal(events.filter(event => event.type === 'model_text_delta').map(event => event.text).join(''), '公开行动');
});

test('Step client rejects truncated completions', async () => {
  const client = createStepClient({ apiKey: 'test-only', fetchImpl: async () => ({ ok: true, json: async () => ({ choices: [{ finish_reason: 'length', message: { role: 'assistant', content: '{' } }] }) }) });
  await assert.rejects(client.complete([], [], { deadline: Date.now() + 3000 }), error => error.code === 'invalid_completion');
});

test('Step client opens a short circuit after repeated authentication failures', async () => {
  let requests = 0;
  const client = createStepClient({ apiKey: 'test-only', fetchImpl: async () => { requests += 1; return { ok: false, status: 401 }; } });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await assert.rejects(client.complete([], [], { deadline: Date.now() + 3000 }), error => error.code === 'http_401');
  }
  await assert.rejects(client.complete([], [], { deadline: Date.now() + 3000 }), error => error.code === 'circuit_open');
  assert.equal(requests, 3);
});

test('HTTP-compatible Step client passes tool results back through the full agent loop', async () => {
  const selected = ['sz-nantou', 'sz-baoanbay', 'sz-gankeng', 'sz-dafen', 'sz-huaqiangbei', 'sz-lianhuashan', 'sz-museum'];
  let requests = 0;
  const fetchImpl = async (_url, options) => {
    const body = JSON.parse(options.body);
    requests += 1;
    assert.equal(body.tool_choice, requests === 4 ? 'auto' : 'required');
    const advertised = body.tools.map(tool => tool.function.name);
    if (requests === 1) {
      assert.deepEqual(advertised, ['ask_question', 'set_trip_spec', 'discover_places', 'resolve_origin']);
      assert.ok(JSON.stringify(body.messages).includes(request.query));
    }
    if (requests === 2) {
      assert.deepEqual(advertised, ['ask_question', 'search_transport', 'search_stays']);
      const results = body.messages.filter(message => message.role === 'tool').map(message => JSON.parse(message.content));
      assert.ok(results.every(result => !Object.hasOwn(result, 'locationDetected') && !Object.hasOwn(result, 'excludedVisitedCount')));
    }
    if (requests === 3) {
      assert.deepEqual(advertised, ['ask_question', 'draft_plan']);
      const stayResult = JSON.parse(body.messages.find(message => message.tool_call_id === 'stays').content);
      assert.ok(!Object.hasOwn(stayResult, 'brands') && !Object.hasOwn(stayResult, 'budget'));
    }
    if (requests === 4) {
      assert.deepEqual(advertised, ['search_attractions', 'search_dining', 'explore_ground']);
      assert.equal(body.model, 'step-5-preview');
      assert.ok(body.messages.some(message => message.role === 'tool' && message.tool_call_id === 'draft'));
    }
    const choice = requests === 1
      ? { finish_reason: 'tool_calls', message: tools(
        call('set_trip_spec', { destination: '深圳', days: 3 }, 'spec'),
        call('resolve_origin', {}, 'origin'),
        call('discover_places', {}, 'places'),
      ).message }
      : requests === 2 ? { finish_reason: 'tool_calls', message: tools(
        call('search_transport', {}, 'transport'),
        call('search_stays', {}, 'stays'),
      ).message }
      : requests === 3 ? { finish_reason: 'tool_calls', message: tools(call('draft_plan', { placeIds: selected }, 'draft')).message }
      : { finish_reason: 'stop', message: final.message };
    return { ok: true, json: async () => ({ choices: [choice], usage: { prompt_tokens: 20, completion_tokens: 5 } }) };
  };
  const model = createStepClient({ apiKey: 'test-only', fetchImpl });
  const plan = await runTravelAgent(request, { model, providers: stubProviders() });
  assert.equal(requests, 4);
  assert.equal(plan.agentRun.status, 'completed');
  assert.equal(plan.agentRun.modelTurns, 4);
  assert.equal(plan.agentRun.usage.prompt_tokens, 80);
});
