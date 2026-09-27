import http from 'node:http';
import { runTravelAgent } from './agent.mjs';
import { providerAvailability } from './providers.mjs';
import { STEP_MODEL } from './step-client.mjs';

const MAX_BODY_BYTES = 256 * 1024;

function httpError(status, message) {
  return Object.assign(new Error(message), { status });
}

function respond(res, status, payload, origin) {
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  };
  if (origin) {
    headers['Access-Control-Allow-Origin'] = origin;
    headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
    headers['Access-Control-Allow-Headers'] = 'Content-Type';
    headers.Vary = 'Origin';
  }
  res.writeHead(status, headers);
  res.end(status === 204 ? undefined : JSON.stringify(payload));
}

async function readJson(req) {
  if (!/^application\/json(?:\s*;|\s*$)/i.test(req.headers['content-type'] || '')) {
    throw httpError(415, '请求必须使用 application/json');
  }
  const chunks = [];
  let bytes = 0;
  for await (const chunk of req) {
    bytes += chunk.length;
    if (bytes <= MAX_BODY_BYTES) chunks.push(chunk);
  }
  if (bytes > MAX_BODY_BYTES) throw httpError(413, '请求过大');
  let input;
  try { input = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw httpError(400, '请求不是有效 JSON'); }
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw httpError(400, '请求必须是 JSON 对象');
  }
  return input;
}

export function createRequestHandler({
  model = null,
  runAgent = runTravelAgent,
  availability = providerAvailability,
  mediaHandler = null,
  allowedOrigin = process.env.CORS_ALLOWED_ORIGIN || '',
} = {}) {
  return async (req, res) => {
    if (req.url?.startsWith('/api/media/')) {
      const handle = mediaHandler || (await import('./media/routes.mjs')).handleMediaRequest;
      return handle(req, res);
    }
    const origin = allowedOrigin && req.headers.origin === allowedOrigin ? allowedOrigin : null;
    if (req.method === 'OPTIONS') return respond(res, 204, null, origin);
    if (req.method === 'GET' && req.url === '/api/health') {
      return respond(res, 200, { ok: true, model: { id: STEP_MODEL, configured: Boolean(model) }, providers: availability() }, origin);
    }
    if (req.method === 'POST' && req.url === '/api/plan') {
      try {
        const result = await runAgent(await readJson(req), { model });
        return respond(res, result.status || 200, result, origin);
      } catch (error) {
        return respond(res, error.status || 500, { error: error.status ? error.message : '规划服务发生内部错误' }, origin);
      }
    }
    return respond(res, 404, { error: '未找到接口' }, origin);
  };
}

export function createApiServer(options) {
  return http.createServer(createRequestHandler(options));
}
