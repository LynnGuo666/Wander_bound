import http from 'node:http';
import { runTravelAgent } from './agent.mjs';
import { providerAvailability } from './providers.mjs';
import { createStepClient, STEP_MODEL } from './step-client.mjs';

const port = Number(process.env.PORT || 4174);
const host = process.env.HOST || '127.0.0.1';
const model = createStepClient();

function respond(res, status, payload) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(payload));
}

async function readJson(req) {
  let input = '';
  for await (const chunk of req) {
    input += chunk;
    if (input.length > 262144) { const error = new Error('请求过大'); error.status = 413; throw error; }
  }
  try { return JSON.parse(input || '{}'); }
  catch { const error = new Error('请求不是有效 JSON'); error.status = 400; throw error; }
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return respond(res, 204, {});
  if (req.method === 'GET' && req.url === '/api/health') {
    return respond(res, 200, { ok: true, model: { id: STEP_MODEL, configured: Boolean(model) }, providers: providerAvailability() });
  }
  if (req.method === 'POST' && req.url === '/api/plan') {
    try {
      const result = await runTravelAgent(await readJson(req), { model });
      return respond(res, result.status || 200, result);
    } catch (error) {
      return respond(res, error.status || 500, { error: error.status ? error.message : '规划服务发生内部错误' });
    }
  }
  return respond(res, 404, { error: '未找到接口' });
});

server.listen(port, host, () => console.log(`Travel Agent API: http://${host}:${port} · ${STEP_MODEL} ${model ? 'enabled' : 'unconfigured'}`));
