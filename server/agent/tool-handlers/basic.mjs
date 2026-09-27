import { toolError } from '../definitions.mjs';
import { addDays, cleanCity, cleanInterests, validDate } from '../request.mjs';

function compactPlaces(places) {
  return places.slice(0, 45).map(place => ({ id: place.id, name: place.name, area: place.area, category: place.category, duration: place.duration }));
}

export async function setTripSpec(ctx, args = {}) {
  const { state, explicitDestination, explicitDays, input } = ctx;
  const fields = ['destination', 'originCity', 'days', 'startDate', 'totalBudgetCny', 'requiredStays', 'interests'];
  if (!fields.some(field => Object.hasOwn(args, field))) return toolError('empty_spec', '请提交本次确认的行程字段');
  const destination = explicitDestination || (Object.hasOwn(args, 'destination') ? cleanCity(args.destination) : state.destination);
  const originCity = cleanCity(input.originCity || (Object.hasOwn(args, 'originCity') ? args.originCity : state.originCity));
  const days = explicitDays ?? (Object.hasOwn(args, 'days') ? Number(args.days) : state.days);
  const startDate = input.startDate || (Object.hasOwn(args, 'startDate') ? String(args.startDate) : state.startDate);
  const budget = Object.hasOwn(args, 'totalBudgetCny') ? Number(args.totalBudgetCny) : state.totalBudgetCny;
  if (Object.hasOwn(args, 'destination') && !destination) return toolError('invalid_destination', '目的地无效');
  if (Object.hasOwn(args, 'originCity') && !originCity) return toolError('invalid_origin', '出发城市无效');
  if (days !== null && (!Number.isInteger(days) || days < 1 || days > 21)) return toolError('invalid_days', '旅行总天数须为 1–21 天');
  if (!validDate(startDate)) return toolError('invalid_date', '出发日期无效');
  if (budget !== null && (!Number.isFinite(budget) || budget < 0 || budget > 1_000_000)) return toolError('invalid_budget', '总预算无效');
  if (Object.hasOwn(args, 'requiredStays') && !Array.isArray(args.requiredStays)) return toolError('invalid_stay', '停留日期必须是数组');
  const requiredStays = Array.isArray(args.requiredStays) ? args.requiredStays.slice(0, 8).map(item => ({ city: cleanCity(item.city), from: String(item.from || ''), to: String(item.to || '') })) : state.requiredStays;
  const endDate = days === null ? null : addDays(startDate, days - 1);
  if (requiredStays.some(stay => !stay.city || !validDate(stay.from) || !validDate(stay.to) || stay.from > stay.to || (endDate && (stay.from < startDate || stay.to > endDate)))) {
    return toolError('invalid_stay', '必须停留的日期不在旅行起止日期内');
  }
  if (destination && requiredStays.some(stay => stay.city !== destination)) return toolError('multi_city_stay', '当前需要逐城指定旅行日期后才能编排多个停留城市');
  const changed = destination !== state.destination || originCity !== state.originCity || days !== state.days || startDate !== state.startDate;
  if (changed && (state.placesDone || state.originDone)) {
    state.places = []; state.flights = []; state.returnFlights = []; state.trains = []; state.returnTrains = []; state.hotels = []; state.plan = null;
    state.originDone = false; state.placesDone = false; state.transportDone = false; state.staysDone = false;
    state.attractionsDone = false; state.diningDone = false; state.groundDone = false; state.drafts = 0;
    ctx.cache.clear();
  }
  state.destination = destination;
  state.days = days;
  state.startDate = startDate;
  state.originCity = originCity;
  state.totalBudgetCny = budget;
  state.requiredStays = requiredStays;
  if (Object.hasOwn(args, 'interests')) state.desiredInterests = cleanInterests(args.interests);
  state.answerNeedsCommit = false;
  return { ok: true, destination, originCity: state.originCity, days, startDate, endDate, totalBudgetCny: budget, requiredStays, interests: state.desiredInterests };
}

export async function askQuestion(ctx, args = {}) {
  const question = typeof args.question === 'string' ? args.question.trim().slice(0, 240) : '';
  const options = Array.isArray(args.options) ? args.options.slice(0, 5).map((item, index) => ({
    id: String(item?.id || `option-${index + 1}`).slice(0, 40), label: String(item?.label || '').trim().slice(0, 80),
    description: String(item?.description || '').trim().slice(0, 160),
  })).filter(item => item.label && item.id !== 'other') : [];
  if (!question || options.length < 2 || new Set(options.map(item => item.id)).size !== options.length) return toolError('invalid_question', '请提供问题和 2–5 个不同的选项');
  ctx.state.pendingQuestion = { id: `ask-${Date.now()}`, question, options: [...options, { id: 'other', label: '其他', description: '输入自己的答案' }] };
  return { ok: true, waitingForUser: true, question: ctx.state.pendingQuestion };
}

export async function resolveOrigin(ctx, args = {}) {
  const { state, input, providers, warnings } = ctx;
  const lat = Number(input.location?.lat);
  const lng = Number(input.location?.lng);
  if (!state.originCity && Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 && input.location && state.providerStatus.amap.configured) {
    try {
      const detected = await providers.reverseLocation({ lat, lng });
      if (detected) { state.originCity = cleanCity(detected); state.locationDetected = true; }
    } catch (error) { warnings.push('位置反查失败，使用手填城市'); state.providerStatus.amap.result = error.message; }
  }
  state.originDone = true;
  return { ok: true, originCity: state.originCity, locationDetected: state.locationDetected };
}

export async function discoverPlaces(ctx, args = {}) {
  const { state, providers, memory, warnings } = ctx;
  if (!state.destination) { return toolError('missing_destination', '请先确定目的地'); }
  if (!state.providerStatus.amap?.configured) {
    state.placesDone = true;
    return toolError('no_place_source', '未配置高德 Key，无法核实目的地地点；请在设置中配置高德 Web 服务 Key');
  }
  try {
    const found = await providers.searchAmapPlaces(state.destination);
    state.places = Array.isArray(found) ? found.filter(place => place?.id && Number.isFinite(place.lat) && Number.isFinite(place.lng)) : [];
    state.providerStatus.amap.result = state.places.length ? 'ok' : '本次无地点结果';
  }
  catch (error) { state.providerStatus.amap.result = error.message; state.places = []; warnings.push('地点查询失败'); }
  state.placesDone = true;
  const available = state.places
    .filter(place => !memory.visitedPlaces.some(visited => visited.id === place.id || (visited.name === place.name && visited.city === state.destination)));
  state.availableCount = available.length;
  if (!state.places.length) {
    return { ok: true, places: [], excludedVisitedCount: 0 };
  }
  return available.length
    ? { ok: true, places: compactPlaces(available), excludedVisitedCount: memory.visitedPlaces.filter(place => place.city === state.destination).length }
    : toolError('no_new_places', `没有可核实的${state.destination}新地点`);
}
