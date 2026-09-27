const TOOL_NAMES = ['set_trip_spec', 'resolve_origin', 'discover_places', 'search_transport', 'search_stays', 'draft_plan', 'search_attractions', 'search_dining', 'explore_ground'];

export const AGENT_TOOLS = [
  { type: 'function', function: { name: 'set_trip_spec', description: '从用户需求确认目的地、天数和兴趣。表单中明确填写的值优先。', parameters: { type: 'object', properties: {
    destination: { type: 'string', description: '城市名，如深圳' }, days: { type: 'integer', description: '1 到 7 天' },
    interests: { type: 'array', items: { type: 'string' }, description: '旅行兴趣分类' },
  }, required: ['destination', 'days'] } } },
  { type: 'function', function: { name: 'resolve_origin', description: '识别出发城市。若有定位且服务已开通会反查；否则使用手填城市。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'discover_places', description: '取得目的地真实候选地点及已到访排除列表。必须在草拟行程前调用。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'search_transport', description: '通过飞猪 Skill、途牛 MCP 和已配置来源查询航班与火车票，比较价格和红眼时间。需要先识别出发城市。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'search_stays', description: '按景点分布、品牌和预算查询住宿区域与真实酒店报价。需要先发现地点。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'draft_plan', description: '使用已取得的地点 ID 草拟并校验行程；不得填写地点名、价格或评分。校验失败后可以修改 ID 再调用一次。', parameters: { type: 'object', properties: {
    placeIds: { type: 'array', items: { type: 'string' }, description: '来自 discover_places 的地点 ID，按偏好选足所需数量' },
  }, required: ['placeIds'] } } },
  { type: 'function', function: { name: 'search_attractions', description: '在行程草拟完成后，通过飞猪 Skill 与途牛 MCP 查询所选景区的门票产品与来源。无报价时返回空列表。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'search_dining', description: '行程草拟完成后，按每天的游玩地点查询附近真实餐饮 POI，返回评分、人均及照片来源；无数据时保持空白。', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'explore_ground', description: '行程草拟完成后，核实步行和公交分段、换乘站、用时。实景影像仅由 iOS 端在有覆盖时请求。', parameters: { type: 'object', properties: {} } } },
];

const definitions = new Map(AGENT_TOOLS.map(tool => [tool.function.name, tool]));

export function availableToolsFor(state) {
  const names = [];
  if (!state.placesDone) names.push('set_trip_spec', 'discover_places');
  if (!state.originDone) names.push('resolve_origin');
  if (state.placesDone && state.originDone && !state.transportDone) names.push('search_transport');
  if (state.placesDone && !state.staysDone) names.push('search_stays');
  if (!state.plan && state.placesDone && state.originDone && state.transportDone && state.staysDone && state.drafts < 2) names.push('draft_plan');
  if (state.plan) {
    if (!state.attractionsDone) names.push('search_attractions');
    if (!state.diningDone) names.push('search_dining');
    if (!state.groundDone) names.push('explore_ground');
  }
  return names.map(name => definitions.get(name));
}

export function toolError(code, message) { return { ok: false, code, message }; }

export function cleanToolArguments(call) {
  if (!TOOL_NAMES.includes(call.function?.name)) return toolError('unknown_tool', '未知工具');
  try {
    const args = JSON.parse(call.function.arguments || '{}');
    return args && typeof args === 'object' && !Array.isArray(args) ? args : toolError('invalid_arguments', '工具参数必须是对象');
  } catch { return toolError('invalid_arguments', '工具参数不是有效 JSON'); }
}
