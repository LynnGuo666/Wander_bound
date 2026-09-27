import { providerAvailability } from './providers/status.mjs';
import { listOtaMcpTools } from './ota/run-cli.mjs';
import { listRailMcpTools } from './providers/rail12306.mjs';

function toolRows(payload) {
  const tools = payload?.result?.tools || payload?.tools;
  return Array.isArray(tools) ? tools.flatMap(tool => tool?.name
    ? [{ name: tool.name, description: String(tool.description || '').slice(0, 400), inputSchema: tool.inputSchema || null }] : []) : [];
}

async function discoverDida(key, fetchImpl = fetch) {
  const endpoint = process.env.TRAVEL_DIDA_MCP_URL;
  if (!key && !endpoint) return { kind: 'MCP', discovery: 'authentication_required', tools: [], metadataSource: 'tools/list' };
  try {
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(key ? { Authorization: `Bearer ${key}`, 'X-Dida-Key': key } : {}),
    };
    const response = await fetchImpl(endpoint || 'https://mcp.rollinggo.cn/mcp', {
      method: 'POST', signal: AbortSignal.timeout(8000), headers,
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} }),
    });
    if (!response.ok) return { kind: 'MCP', discovery: 'failed', error: `http_${response.status}`, tools: [], metadataSource: 'tools/list' };
    const body = await response.text();
    const records = body.trim().startsWith('data:') ? body.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).filter(line => line !== '[DONE]') : [body];
    const tools = toolRows(JSON.parse(records.at(-1)));
    return { kind: 'MCP', discovery: tools.length ? 'runtime' : 'empty', tools,
      metadataSource: endpoint ? 'tools/list（Docker 道旅 MCP）' : 'tools/list（已认证连接）' };
  } catch { return { kind: 'MCP', discovery: 'failed', error: 'discovery_failed', tools: [], metadataSource: 'tools/list' }; }
}

export async function discoverCapabilities(credentials = {}, { availability = providerAvailability, listOta = listOtaMcpTools, didaDiscovery = discoverDida } = {}) {
  const providers = availability(credentials);
  let ota = { kind: 'MCP', discovery: 'unavailable', tools: [], metadataSource: 'tools/list（Docker OTA MCP）' };
  if (process.env.TRAVEL_OTA_MCP_URL) {
    try {
      const tools = await listOta({ credentials, timeoutMs: 5000 });
      ota = { ...ota, discovery: tools.length ? 'runtime' : 'empty', tools };
    } catch { ota = { ...ota, discovery: 'failed', error: 'discovery_failed' }; }
  }
  const dida = await didaDiscovery(credentials.dida || process.env.DIDA_API_KEY);
  let rail = { kind: 'MCP', discovery: 'unavailable', tools: [], metadataSource: 'tools/list（12306 社区 MCP）' };
  if (process.env.TRAVEL_12306_MCP_URL) {
    try { const tools = await listRailMcpTools({ timeoutMs: 5000 }); rail = { ...rail, discovery: tools.length ? 'runtime' : 'empty', tools }; }
    catch { rail = { ...rail, discovery: 'failed', error: 'discovery_failed' }; }
  }
  return { checkedAt: new Date().toISOString(), providers, connections: { ota, dida, rail } };
}
