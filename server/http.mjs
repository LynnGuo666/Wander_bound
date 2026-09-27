import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { runTravelAgent } from './agent.mjs';
import { createRequestProviders, providerAvailability } from './providers.mjs';
import { createStepClient, STEP_MODEL, stepChannel } from './step-client.mjs';
import { discoverCapabilities } from './capabilities.mjs';
import { defaultConfigStore } from './config.mjs';

const MAX_BODY_BYTES = 256 * 1024;
const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const KEY_NAMES = ['stepfun', 'amap', 'dida', 'duffel', 'tuniu', 'flyai'];

function extractCredentials(input) {
  const supplied = input.credentials;
  if (supplied == null) return {};
  if (!supplied || typeof supplied !== 'object' || Array.isArray(supplied)) throw httpError(400, '密钥格式无效');
  const credentials = {};
  for (const name of KEY_NAMES) {
    const value = supplied[name];
    if (value == null || value === '') continue;
    if (typeof value !== 'string' || value.length > 512 || /[\r\n\x00-\x1f]/.test(value)) throw httpError(400, '密钥格式无效');
    credentials[name] = value.trim();
  }
  return credentials;
}

async function serveApp(req, res) {
  if (!['GET', 'HEAD'].includes(req.method) || !req.url || req.url.startsWith('/api/')) return false;
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); }
  catch { return false; }
  if (pathname.includes('..') || pathname.includes('\\')) return false;
  const file = pathname === '/' ? 'index.html' : pathname.slice(1);
  const filename = path.join(DIST, file);
  if (!filename.startsWith(DIST)) return false;
  try {
    if (!(await stat(filename)).isFile()) return false;
    const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.png') ? 'image/png' : 'text/html';
    res.writeHead(200, { 'Content-Type': `${type}; charset=utf-8`, 'Cache-Control': file.startsWith('assets/') ? 'public, max-age=31536000, immutable' : 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(req.method === 'HEAD' ? undefined : await readFile(filename));
    return true;
  } catch { return false; }
}

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
    headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS';
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
  modelFactory = createStepClient,
  runAgent = runTravelAgent,
  availability = providerAvailability,
  configStore = defaultConfigStore,
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
    if (req.method === 'GET' && req.url === '/api/settings') {
      try { return respond(res, 200, await configStore.public(), origin); }
      catch { return respond(res, 500, { error: '无法读取设置' }, origin); }
    }
    if (req.method === 'PUT' && req.url === '/api/settings') {
      try { return respond(res, 200, await configStore.update(await readJson(req)), origin); }
      catch (error) { return respond(res, error.status || 500, { error: error.status ? error.message : '无法保存设置' }, origin); }
    }
    if (req.method === 'GET' && req.url === '/api/health') {
      try {
        const config = await configStore.read();
        return respond(res, 200, { ok: true, model: { id: STEP_MODEL, configured: Boolean(config.credentials.stepfun || model), channel: model?.channel || stepChannel() }, providers: availability(config.credentials) }, origin);
      } catch { return respond(res, 500, { error: '无法读取设置' }, origin); }
    }
    if (req.method === 'POST' && req.url === '/api/capabilities') {
      try {
        const input = await readJson(req);
        const config = await configStore.read();
        const credentials = { ...config.credentials, ...extractCredentials(input) };
        return respond(res, 200, await discoverCapabilities(credentials), origin);
      } catch (error) { return respond(res, error.status || 500, { error: error.status ? error.message : '能力发现失败' }, origin); }
    }
    if (req.method === 'POST' && (req.url === '/api/plan' || req.url === '/api/plan/stream')) {
      const stream = req.url.endsWith('/stream');
      try {
        const input = await readJson(req);
        const config = await configStore.read();
        const credentials = { ...config.credentials, ...extractCredentials(input) };
        const { credentials: _removed, ...request } = input;
        const requestModel = credentials.stepfun ? modelFactory({ apiKey: credentials.stepfun }) : model;
        const providers = createRequestProviders(credentials);
        const controller = stream ? new AbortController() : null;
        if (stream) {
          const headers = { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' };
          if (origin) headers['Access-Control-Allow-Origin'] = origin;
          res.writeHead(200, headers);
          res.write(': connected\n\n');
          res.on('close', () => controller.abort());
        }
        const emit = event => { if (stream && !res.writableEnded && !res.destroyed) res.write(`event: progress\ndata: ${JSON.stringify(event)}\n\n`); };
        const result = await runAgent(request, { model: requestModel, providers, providerPriority: config.priorities, onEvent: emit, signal: controller?.signal });
        if (stream) { res.end(`event: result\ndata: ${JSON.stringify(result)}\n\n`); return; }
        return respond(res, result.status || 200, result, origin);
      } catch (error) {
        if (stream && res.destroyed) return;
        if (stream && res.headersSent) { res.end(`event: result\ndata: ${JSON.stringify({ error: error.status ? error.message : '规划服务发生内部错误' })}\n\n`); return; }
        return respond(res, error.status || 500, { error: error.status ? error.message : '规划服务发生内部错误' }, origin);
      }
    }
    if (await serveApp(req, res)) return;
    return respond(res, 404, { error: '未找到接口' }, origin);
  };
}

export function createApiServer(options) {
  return http.createServer(createRequestHandler(options));
}
