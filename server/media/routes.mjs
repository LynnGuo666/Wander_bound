import { timingSafeEqual } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createMediaStore } from './store.mjs';
import { createMemoryService } from './memories.mjs';

const MAX_UPLOAD = 15 * 1024 * 1024;

function reply(res, status, value, contentType = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': contentType, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(Buffer.isBuffer(value) ? value : JSON.stringify(value));
}

async function body(req, limit) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw Object.assign(new Error('请求内容过大'), { status: 413 });
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function jsonBody(req) {
  if (!/^application\/json(?:\s*;|\s*$)/i.test(req.headers['content-type'] || '')) {
    throw Object.assign(new Error('请求必须使用 application/json'), { status: 415 });
  }
  try { return JSON.parse((await body(req, 64 * 1024)).toString('utf8')); }
  catch (error) { if (error.status) throw error; throw Object.assign(new Error('JSON 无效'), { status: 400 }); }
}

function authorized(provided, expected) {
  const token = /^Bearer (.+)$/.exec(provided || '')?.[1] || '';
  const left = Buffer.from(token);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function createMediaHandler({
  token = process.env.MEDIA_API_TOKEN || '',
  store = createMediaStore(),
  memory = createMemoryService({ store }),
} = {}) {
  return async (req, res) => {
    if (!token) return reply(res, 503, { error: '媒体服务尚未配置访问令牌' });
    if (!authorized(req.headers.authorization, token)) return reply(res, 401, { error: '媒体服务需要有效令牌' });
    const url = new URL(req.url, 'http://localhost');
    const parts = url.pathname.split('/').filter(Boolean);
    try {
      if (req.method === 'GET' && url.pathname === '/api/media/health') {
        return reply(res, 200, { ok: true, storage: 'private-local', imageProcessor: 'sharp', videoBackend: memory.configured ? 'dgx-spark-minimax-h3' : 'unconfigured' });
      }
      if (req.method === 'POST' && url.pathname === '/api/media/photos') {
        if (req.headers['content-type'] !== 'image/jpeg') return reply(res, 415, { error: '仅接收已在设备上导出的 JPEG 图片' });
        const photo = await store.addPhoto(await body(req, MAX_UPLOAD), {
          tripId: req.headers['x-trip-id'], capturedDay: req.headers['x-captured-day'],
        });
        return reply(res, 201, photo);
      }
      if (req.method === 'GET' && url.pathname === '/api/media/photos') {
        return reply(res, 200, { photos: await store.listPhotos(url.searchParams.get('tripId')) });
      }
      if (parts.length === 4 && parts[0] === 'api' && parts[1] === 'media' && parts[2] === 'photos' && req.method === 'GET') {
        const bytes = await store.photoBytes(parts[3], url.searchParams.get('variant') || 'original');
        return bytes ? reply(res, 200, bytes, 'image/jpeg') : reply(res, 404, { error: '照片不存在' });
      }
      if (parts.length === 5 && parts[0] === 'api' && parts[1] === 'media' && parts[2] === 'photos' && parts[4] === 'enhance' && req.method === 'POST') {
        const input = await jsonBody(req);
        const photo = await store.enhance(parts[3], input?.preset);
        return photo ? reply(res, 200, photo) : reply(res, 404, { error: '照片不存在' });
      }
      if (req.method === 'POST' && url.pathname === '/api/media/memories') {
        const input = await jsonBody(req);
        const job = await memory.create(input || {});
        return reply(res, 202, { id: job.id, status: job.status, backend: job.backend });
      }
      if (parts.length >= 4 && parts[0] === 'api' && parts[1] === 'media' && parts[2] === 'memories' && req.method === 'GET') {
        if (parts.length === 5 && parts[4] === 'video') {
          const video = await memory.videoPath(parts[3]);
          if (!video) return reply(res, 404, { error: '视频尚未生成' });
          res.writeHead(200, { 'Content-Type': 'video/mp4', 'Content-Length': (await stat(video)).size,
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
          createReadStream(video).pipe(res);
          return;
        }
        if (parts.length === 4) {
          const job = await memory.get(parts[3]);
          return job ? reply(res, 200, { id: job.id, status: job.status, backend: job.backend, error: job.error || null })
            : reply(res, 404, { error: '任务不存在' });
        }
      }
      return reply(res, 404, { error: '未找到媒体接口' });
    } catch (error) {
      return reply(res, error.status || 500, { error: error.status ? error.message : '媒体处理失败' });
    }
  };
}

let defaultHandler;
export async function handleMediaRequest(req, res) {
  defaultHandler ||= createMediaHandler();
  return defaultHandler(req, res);
}
