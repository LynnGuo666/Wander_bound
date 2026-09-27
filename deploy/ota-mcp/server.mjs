import http from 'node:http';
import { spawn } from 'node:child_process';

const PORT = Number(process.env.PORT || 4176);
const MAX_BODY = 128 * 1024;
const MAX_OUTPUT = 2_000_000;
const tools = [
  { name: 'flyai_search_flight', description: '飞猪 FlyAI 只读机票查询，返回供应商航班、时刻和其提供的票价。', inputSchema: { type: 'object', properties: { origin: { type: 'string' }, destination: { type: 'string' }, date: { type: 'string' } }, required: ['origin', 'destination', 'date'] } },
  { name: 'flyai_search_train', description: '飞猪 FlyAI 只读火车票查询，返回车次、时刻；遮蔽价格保持未知。', inputSchema: { type: 'object', properties: { origin: { type: 'string' }, destination: { type: 'string' }, date: { type: 'string' } }, required: ['origin', 'destination', 'date'] } },
  { name: 'flyai_search_poi', description: '飞猪 FlyAI 只读景点/门票地点查询，返回匹配的地点和门票信息。', inputSchema: { type: 'object', properties: { city: { type: 'string' }, keyword: { type: 'string' } }, required: ['city'] } },
  { name: 'tuniu_search_flight', description: '途牛 flight.searchLowestPriceFlight 只读国内机票查询；需要途牛认证。', inputSchema: { type: 'object', properties: { departureCityName: { type: 'string' }, arrivalCityName: { type: 'string' }, departureDate: { type: 'string' } }, required: ['departureCityName', 'arrivalCityName', 'departureDate'] } },
  { name: 'tuniu_search_train', description: '途牛 train.searchLowestPriceTrain 只读火车票查询；需要途牛认证。', inputSchema: { type: 'object', properties: { departureCityName: { type: 'string' }, arrivalCityName: { type: 'string' }, departureDate: { type: 'string' } }, required: ['departureCityName', 'arrivalCityName', 'departureDate'] } },
  { name: 'tuniu_search_ticket', description: '途牛 ticket.query_cheapest_tickets 只读景区门票查询；需要途牛认证。', inputSchema: { type: 'object', properties: { scenic_name: { type: 'string' }, depart_date: { type: 'string' } }, required: ['scenic_name'] } },
];
const definitions = new Map(tools.map(tool => [tool.name, tool]));

function clean(value, max = 100) {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\x00-\x1f]/.test(value)) throw new Error('无效工具参数');
  return value.trim();
}

function commandFor(name, args) {
  if (!definitions.has(name) || !args || typeof args !== 'object' || Array.isArray(args)) throw new Error('不支持的工具');
  if (name === 'flyai_search_poi') return ['flyai', ['search-poi', '--city-name', clean(args.city), ...(args.keyword ? ['--keyword', clean(args.keyword)] : [])]];
  if (name.startsWith('flyai_')) return ['flyai', [name === 'flyai_search_flight' ? 'search-flight' : 'search-train', '--origin', clean(args.origin), '--destination', clean(args.destination), '--dep-date', clean(args.date, 10), '--sort-type', '3']];
  const server = { tuniu_search_flight: 'flight', tuniu_search_train: 'train', tuniu_search_ticket: 'ticket' }[name];
  const tool = { flight: 'searchLowestPriceFlight', train: 'searchLowestPriceTrain', ticket: 'query_cheapest_tickets' }[server];
  const input = server === 'ticket'
    ? { scenic_name: clean(args.scenic_name), ...(args.depart_date ? { depart_date: clean(args.depart_date, 10) } : {}) }
    : { departureCityName: clean(args.departureCityName), arrivalCityName: clean(args.arrivalCityName), departureDate: clean(args.departureDate, 10) };
  return ['tuniu', ['call', server, tool, '-a', JSON.stringify(input)]];
}

function callCli(binary, args, credentials) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (credentials.flyai) env.FLYAI_API_KEY = credentials.flyai;
    if (credentials.tuniu) env.TUNIU_API_KEY = credentials.tuniu;
    const child = spawn(`/app/node_modules/.bin/${binary}`, args, { shell: false, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    const timer = setTimeout(() => child.kill('SIGKILL'), 18000);
    child.stdout.on('data', chunk => { stdout = (stdout + chunk.toString()).slice(0, MAX_OUTPUT + 1); if (stdout.length > MAX_OUTPUT) child.kill('SIGKILL'); });
    child.stderr.resume();
    child.on('error', reject);
    child.on('close', code => {
      clearTimeout(timer);
      if (code !== 0 || stdout.length > MAX_OUTPUT) return reject(new Error(`${binary} 查询失败（${code ?? '超时'}）`));
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error('供应商返回非 JSON')); }
    });
  });
}

function response(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') return response(res, 200, { ok: true, server: 'travel-ota-mcp', tools: tools.length });
  if (req.method !== 'POST' || req.url !== '/mcp') return response(res, 404, { error: 'not_found' });
  try {
    let raw = '';
    for await (const chunk of req) { raw += chunk.toString(); if (raw.length > MAX_BODY) throw new Error('请求过大'); }
    const message = JSON.parse(raw);
    if (message?.jsonrpc !== '2.0' || typeof message.method !== 'string') throw new Error('无效 MCP 请求');
    if (message.method === 'notifications/initialized') { res.writeHead(202); res.end(); return; }
    const result = message.method === 'initialize'
      ? { protocolVersion: '2025-03-26', capabilities: { tools: { listChanged: false } }, serverInfo: { name: 'travel-ota-mcp', version: '0.1.0' } }
      : message.method === 'tools/list' ? { tools }
      : message.method === 'tools/call' ? await (async () => {
        const [binary, args] = commandFor(message.params?.name, message.params?.arguments);
        const value = await callCli(binary, args, { flyai: req.headers['x-flyai-key'], tuniu: req.headers['x-tuniu-key'] });
        return { content: [{ type: 'text', text: JSON.stringify(value) }], isError: false };
      })()
      : message.method === 'ping' ? {} : null;
    if (result === null) return response(res, 200, { jsonrpc: '2.0', id: message.id ?? null, error: { code: -32601, message: 'method_not_found' } });
    return response(res, 200, { jsonrpc: '2.0', id: message.id ?? null, result });
  } catch (error) {
    return response(res, 200, { jsonrpc: '2.0', id: null, error: { code: -32000, message: String(error.message || 'tool_failed').slice(0, 180) } });
  }
});

server.listen(PORT, '0.0.0.0');
