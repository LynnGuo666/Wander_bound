import http from 'node:http';

// 道旅 RollingGo 酒店搜索的只读 MCP 封装。容器不保存任何凭据：
// 每次请求经 X-Dida-Key 头带入，转发到上游官方 MCP（searchHotels）。
const PORT = Number(process.env.PORT || 4178);
const UPSTREAM = process.env.DIDA_UPSTREAM_URL || 'https://mcp.rollinggo.cn/mcp';
const MAX_BODY = 64 * 1024;
const MAX_OUTPUT = 2_000_000;

const tools = [
  {
    name: 'dida_search_hotels',
    description: '道旅 RollingGo 只读酒店搜索，返回酒店名称、坐标、星级、查询时总价与预订链接；需要道旅认证。',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: '城市名，如：深圳' },
        area: { type: 'string', description: '住宿区域名，如：南山；可省略' },
        checkInDate: { type: 'string', description: '入住日期 YYYY-MM-DD' },
        stayNights: { type: 'integer', description: '入住晚数' },
        budget: { type: 'number', description: '每晚预算（人民币元）' },
        size: { type: 'integer', description: '返回条数上限，默认 12' },
      },
      required: ['city', 'checkInDate'],
    },
  },
];
const definitions = new Map(tools.map(tool => [tool.name, tool]));

function clean(value, max = 100) {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\x00-\x1f]/.test(value)) throw new Error('无效工具参数');
  return value.trim();
}

async function searchHotels(args, apiKey) {
  const city = clean(args.city);
  const area = args.area ? clean(args.area) : '';
  const checkInDate = clean(args.checkInDate, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(checkInDate)) throw new Error('入住日期必须是 YYYY-MM-DD');
  const stayNights = Number.isInteger(args.stayNights) && args.stayNights > 0 && args.stayNights <= 30 ? args.stayNights : 1;
  const budget = Number.isFinite(Number(args.budget)) && Number(args.budget) > 0 ? Math.round(Number(args.budget)) : null;
  const size = Number.isInteger(args.size) && args.size > 0 && args.size <= 30 ? args.size : 12;
  const place = `${city}${area}`;
  const arguments_ = {
    originQuery: `${place}附近酒店${budget ? `，每晚不高于${budget}元` : ''}`,
    place, placeType: area ? '区/县' : '城市',
    checkInParam: { checkInDate, stayNights },
    size,
  };
  const response = await fetch(UPSTREAM, {
    method: 'POST',
    signal: AbortSignal.timeout(12000),
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'searchHotels', arguments: arguments_ } }),
  });
  if (!response.ok) throw new Error(`道旅上游 HTTP ${response.status}`);
  const body = await response.text();
  const records = body.trim().startsWith('data:')
    ? body.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).filter(line => line !== '[DONE]')
    : [body];
  let decoded = null;
  for (const record of records.reverse()) {
    try {
      const message = JSON.parse(record);
      if (message.error) throw new Error(`道旅上游 MCP ${String(message.error.code || 'error')}`);
      const result = message.result;
      if (result?.isError) throw new Error('道旅上游返回工具错误');
      const text = result?.content?.find(item => item.type === 'text')?.text;
      if (!text) continue;
      decoded = JSON.parse(text);
      break;
    } catch (error) {
      if (error.message?.startsWith('道旅上游')) throw error;
    }
  }
  if (decoded === null) throw new Error('酒店服务没有返回可解析的数据');
  if (decoded?.success === false) throw new Error(`道旅查询失败：${String(decoded.message || '未知错误').slice(0, 120)}`);
  return decoded;
}

function response(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') return response(res, 200, { ok: true, server: 'travel-dida-mcp', tools: tools.length, upstream: new URL(UPSTREAM).host });
  if (req.method !== 'POST' || req.url !== '/mcp') return response(res, 404, { error: 'not_found' });
  try {
    let raw = '';
    for await (const chunk of req) { raw += chunk.toString(); if (raw.length > MAX_BODY) throw new Error('请求过大'); }
    const message = JSON.parse(raw);
    if (message?.jsonrpc !== '2.0' || typeof message.method !== 'string') throw new Error('无效 MCP 请求');
    if (message.method === 'notifications/initialized') { res.writeHead(202); res.end(); return; }
    const result = message.method === 'initialize'
      ? { protocolVersion: '2025-03-26', capabilities: { tools: { listChanged: false } }, serverInfo: { name: 'travel-dida-mcp', version: '0.1.0' } }
      : message.method === 'tools/list' ? { tools }
      : message.method === 'tools/call' ? await (async () => {
        if (message.params?.name !== 'dida_search_hotels' || !definitions.has(message.params?.name)) throw new Error('不支持的工具');
        const business = await searchHotels(message.params?.arguments, req.headers['x-dida-key']);
        return { content: [{ type: 'text', text: JSON.stringify(business) }], isError: false };
      })()
      : message.method === 'ping' ? {} : null;
    if (result === null) return response(res, 200, { jsonrpc: '2.0', id: message.id ?? null, error: { code: -32601, message: 'method_not_found' } });
    return response(res, 200, { jsonrpc: '2.0', id: message.id ?? null, result });
  } catch (error) {
    return response(res, 200, { jsonrpc: '2.0', id: null, error: { code: -32000, message: String(error.message || 'tool_failed').slice(0, 180) } });
  }
});

server.listen(PORT, '0.0.0.0');
