import http from 'node:http';
import { searchTransport } from '../../server/mcp-data/transport.mjs';
import { searchStays } from '../../server/mcp-data/stays.mjs';
import { searchAttractions } from '../../server/mcp-data/attractions.mjs';
import { searchPlaces } from '../../server/mcp-data/places.mjs';
import { credentialsFromHeaders } from '../../server/mcp-data/validation.mjs';

const string = { type: 'string' };
const integer = { type: 'integer' };
export const tools = [
  { name: 'travel_search_transport', description: '查询去返程真实航班与火车报价，返回供应商状态和完整报价；按请求惰性调用 OTA、12306 MCP 与 Duffel API。',
    inputSchema: { type: 'object', properties: { originCity: string, destination: string, startDate: string, days: integer,
      priorities: { type: 'object' } }, required: ['originCity', 'destination', 'startDate', 'days'] } },
  { name: 'travel_search_stays', description: '通过道旅 MCP 查询酒店，返回真实价格、坐标和预订地址。',
    inputSchema: { type: 'object', properties: { city: string, area: string, checkInDate: string, stayNights: integer,
      budget: { type: 'number' } }, required: ['city', 'checkInDate', 'stayNights'] } },
  { name: 'travel_search_attractions', description: '通过飞猪和途牛 MCP 查询已选景点门票，返回价格及供应商。',
    inputSchema: { type: 'object', properties: { city: string, places: { type: 'array', maxItems: 7,
      items: { type: 'object', properties: { id: string, name: string, visitDate: string }, required: ['id', 'name', 'visitDate'] } },
      priorities: { type: 'object' } }, required: ['city', 'places'] } },
  { name: 'travel_search_places', description: '通过飞猪 MCP 查询城市真实 POI，并在 Node 层标准化。',
    inputSchema: { type: 'object', properties: { city: string }, required: ['city'] } },
];

const handlers = {
  travel_search_transport: searchTransport,
  travel_search_stays: searchStays,
  travel_search_attractions: searchAttractions,
  travel_search_places: searchPlaces,
};

function respond(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

export function createServer() {
  return http.createServer(async (req, res) => {
    if (req.method === 'GET' && req.url === '/health') return respond(res, 200, { ok: true, server: 'travel-data-mcp', tools: tools.length });
    if (req.method !== 'POST' || req.url !== '/mcp') return respond(res, 404, { error: 'not_found' });
    let message;
    try {
      const chunks = [];
      let bytes = 0;
      for await (const chunk of req) { bytes += chunk.length; if (bytes > 128 * 1024) throw new Error('请求过大'); chunks.push(chunk); }
      message = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (message?.jsonrpc !== '2.0' || typeof message.method !== 'string') throw new Error('无效 MCP 请求');
      if (message.method === 'notifications/initialized') { res.writeHead(202); res.end(); return; }
      const result = message.method === 'initialize'
        ? { protocolVersion: '2025-03-26', capabilities: { tools: { listChanged: false } }, serverInfo: { name: 'travel-data-mcp', version: '1.0.0' } }
        : message.method === 'tools/list' ? { tools }
        : message.method === 'tools/call' ? await (async () => {
          const handler = handlers[message.params?.name];
          if (!handler) throw new Error('不支持的 MCP 工具');
          const args = message.params?.arguments;
          if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('工具参数无效');
          const value = await handler(args, credentialsFromHeaders(req.headers));
          return { content: [{ type: 'text', text: JSON.stringify(value) }], structuredContent: value, isError: false };
        })()
        : message.method === 'ping' ? {} : null;
      if (result === null) return respond(res, 200, { jsonrpc: '2.0', id: message.id ?? null, error: { code: -32601, message: 'method_not_found' } });
      return respond(res, 200, { jsonrpc: '2.0', id: message.id ?? null, result });
    } catch (error) {
      return respond(res, 200, { jsonrpc: '2.0', id: message?.id ?? null,
        error: { code: -32000, message: String(error?.message || 'tool_failed').slice(0, 180) } });
    }
  });
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  createServer().listen(Number(process.env.PORT || 4179), '0.0.0.0');
}
