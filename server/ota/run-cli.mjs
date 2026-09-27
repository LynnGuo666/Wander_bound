const endpoint = () => process.env.TRAVEL_OTA_MCP_URL;

export async function callOtaMcp(method, params = {}, { credentials = {}, fetchImpl = fetch, timeoutMs = 20000 } = {}) {
  if (!endpoint()) throw new Error('OTA MCP 服务未配置');
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
  if (credentials.flyai || process.env.FLYAI_API_KEY) headers['X-FlyAI-Key'] = credentials.flyai || process.env.FLYAI_API_KEY;
  if (credentials.tuniu || process.env.TUNIU_API_KEY) headers['X-Tuniu-Key'] = credentials.tuniu || process.env.TUNIU_API_KEY;
  const response = await fetchImpl(endpoint(), {
    method: 'POST', headers, signal: AbortSignal.timeout(timeoutMs),
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  if (!response.ok) throw new Error(`OTA MCP HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error) throw new Error(`OTA MCP ${String(payload.error.code || 'error')}`);
  return payload.result;
}

export async function listOtaMcpTools(options = {}) {
  const result = await callOtaMcp('tools/list', {}, options);
  return Array.isArray(result?.tools) ? result.tools.map(tool => ({ name: tool.name, description: tool.description || '', inputSchema: tool.inputSchema })) : [];
}

function option(args, name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

function mapCliCall(binary, args) {
  if (binary === 'flyai') {
    if (args[0] === 'search-poi') return ['flyai_search_poi', { city: option(args, '--city-name'), keyword: option(args, '--keyword') }];
    if (args[0] === 'search-flight' || args[0] === 'search-train') return [args[0] === 'search-flight' ? 'flyai_search_flight' : 'flyai_search_train',
      { origin: option(args, '--origin'), destination: option(args, '--destination'), date: option(args, '--dep-date') }];
  }
  if (binary === 'tuniu' && args[0] === 'call') {
    const name = { 'flight.searchLowestPriceFlight': 'tuniu_search_flight', 'train.searchLowestPriceTrain': 'tuniu_search_train', 'ticket.query_cheapest_tickets': 'tuniu_search_ticket' }[`${args[1]}.${args[2]}`];
    if (name) return [name, JSON.parse(option(args, '-a') || '{}')];
  }
  throw new Error('未允许的 OTA MCP 工具');
}

// Kept as the adapter boundary for existing provider normalizers; this calls MCP, never a host CLI.
export async function runCli(binary, args, options = {}) {
  const [name, input] = mapCliCall(binary, args);
  const result = await callOtaMcp('tools/call', { name, arguments: input }, options);
  if (result?.isError) throw new Error('OTA MCP 工具返回错误');
  const text = result?.content?.find(item => item.type === 'text')?.text;
  if (!text) throw new Error('OTA MCP 工具没有文本结果');
  try { return JSON.parse(text); } catch { throw new Error('OTA MCP 工具返回非 JSON'); }
}
