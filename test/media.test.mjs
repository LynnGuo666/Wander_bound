import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import sharp from 'sharp';
import { createApiServer } from '../server/http.mjs';
import { createComfyClient } from '../server/media/comfy.mjs';
import { createQwenImageClient } from '../server/media/qwen-image.mjs';
import { createMediaHandler } from '../server/media/routes.mjs';
import { createMediaStore } from '../server/media/store.mjs';

let directory;
let server;
let root;
const token = 'test-media-token';

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), 'travel-media-'));
  const store = createMediaStore(directory);
  server = createApiServer({ mediaHandler: createMediaHandler({ token, store, edits: {
    configured: true,
    create: async input => ({ id: 'edit-test', status: 'running', backend: 'dgx-spark-qwen-image-2.1', seed: input.seed ?? 42 }),
    get: async () => ({ id: 'edit-test', photoId: 'photo-test', status: 'succeeded', backend: 'dgx-spark-qwen-image-2.1', variant: 'ai-edit-test' }),
  }, memory: {
    configured: true,
    create: async input => ({ id: 'job-test', status: 'running', backend: 'dgx-spark-minimax-h3', photoIds: input.photoIds }),
    get: async () => ({ id: 'job-test', status: 'running', backend: 'dgx-spark-minimax-h3' }),
    videoPath: async () => null,
  } }) });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  root = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise(resolve => server.close(resolve));
  await rm(directory, { recursive: true, force: true });
});

test('private photo upload strips metadata, analyzes locally, and produces a separate enhanced version', async () => {
  const source = await sharp({ create: { width: 600, height: 400, channels: 3, background: '#708da8' } })
    .jpeg().withMetadata({ orientation: 6 }).toBuffer();
  const unauthorized = await fetch(`${root}/api/media/photos`, { method: 'POST', body: source });
  assert.equal(unauthorized.status, 401);
  const upload = await fetch(`${root}/api/media/photos`, { method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'image/jpeg', 'X-Trip-Id': 'shenzhen-2026', 'X-Captured-Day': '2026-09-25',
  }, body: source });
  assert.equal(upload.status, 201);
  const photo = await upload.json();
  assert.equal(photo.tripId, 'shenzhen-2026');
  assert.equal(photo.capturedDay, '2026-09-25');
  assert.equal(photo.analysis.processor, '本地 Sharp 图像统计');
  assert.equal(JSON.stringify(photo).includes('latitude'), false);
  const saved = await readFile(path.join(directory, 'photos', `${photo.id}.jpg`));
  assert.equal((await sharp(saved).metadata()).exif, undefined);
  const enhanced = await fetch(`${root}/api/media/photos/${photo.id}/enhance`, { method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'application/json',
  }, body: JSON.stringify({ preset: 'cinematic' }) });
  assert.equal(enhanced.status, 200);
  assert.deepEqual((await enhanced.json()).variants, ['cinematic']);
  const result = await fetch(`${root}/api/media/photos/${photo.id}?variant=cinematic`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('content-type'), 'image/jpeg');
  const listing = await fetch(`${root}/api/media/photos?tripId=shenzhen-2026`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal((await listing.json()).photos.length, 1);
  const redraw = await fetch(`${root}/api/media/photos/${photo.id}/redraw`, { method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'application/json',
  }, body: JSON.stringify({ prompt: '把照片绘制成旅行明信片', seed: 17 }) });
  assert.equal(redraw.status, 202);
  assert.equal((await redraw.json()).seed, 17);
  const edit = await fetch(`${root}/api/media/edits/edit-test`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal((await edit.json()).variant, 'ai-edit-test');
});

test('Qwen image adapter fills prompt, photo and seed without exposing ComfyUI publicly', async () => {
  const workflowPath = path.join(directory, 'qwen-workflow.json');
  await writeFile(workflowPath, JSON.stringify({ '1': { inputs: {
    image: '__TRAVEL_IMAGE__', text: '__TRAVEL_PROMPT__', seed: '__TRAVEL_SEED__',
  } } }));
  const calls = [];
  const client = createQwenImageClient({ baseUrl: 'http://127.0.0.1:8191', workflowPath,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/upload/image')) return { ok: true, json: async () => ({ name: 'travel-test.jpg' }) };
      if (url.endsWith('/prompt')) return { ok: true, json: async () => ({ prompt_id: 'qwen-prompt' }) };
      return { ok: true, json: async () => ({ 'qwen-prompt': { status: { completed: true },
        outputs: { '9': { images: [{ filename: 'edited.png', type: 'output' }] } } } }) };
    } });
  assert.equal(await client.queueEdit(Buffer.from('jpeg'), '绘制成明信片', 17), 'qwen-prompt');
  assert.deepEqual(JSON.parse(calls[1].options.body).prompt['1'].inputs,
    { image: 'travel-test.jpg', text: '<image1> 绘制成明信片', seed: 17 });
  assert.equal((await client.editStatus('qwen-prompt')).file.filename, 'edited.png');
  assert.throws(() => createQwenImageClient({ baseUrl: 'https://public.example', workflowPath }), /私网/);
});

test('a prompt lost after a ComfyUI restart is reported as missing instead of running forever', async () => {
  const workflowPath = path.join(directory, 'qwen-workflow.json');
  const client = createQwenImageClient({ baseUrl: 'http://127.0.0.1:8191', workflowPath,
    fetchImpl: async url => ({ ok: true, json: async () => url.includes('/queue')
      ? { queue_running: [], queue_pending: [] } : {} }) });
  assert.equal((await client.editStatus('lost-prompt')).status, 'missing');
});

test('MiniMax H3 ComfyUI adapter sends sanitized image to private endpoint and uses explicit workflow placeholders', async () => {
  const workflowPath = path.join(directory, 'workflow.json');
  await writeFile(workflowPath, JSON.stringify({ '1': { inputs: { image: '__TRAVEL_IMAGE__', prompt: '__TRAVEL_PROMPT__' } } }));
  const calls = [];
  const client = createComfyClient({ baseUrl: 'http://spark-82.tailb7a50b.ts.net:8188', workflowPath,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/upload/image')) return { ok: true, json: async () => ({ name: 'travel-test.jpg' }) };
      if (url.endsWith('/prompt')) return { ok: true, json: async () => ({ prompt_id: 'prompt-1' }) };
      return { ok: true, json: async () => ({ 'prompt-1': { status: { completed: true }, outputs: { '2': { videos: [{ filename: 'clip.mp4' }] } } } }) };
    } });
  assert.equal(await client.queueClip(Buffer.from('jpeg'), '旅行镜头'), 'prompt-1');
  assert.equal(calls.length, 2);
  assert.equal(JSON.parse(calls[1].options.body).prompt['1'].inputs.image, 'travel-test.jpg');
  assert.equal(JSON.parse(calls[1].options.body).prompt['1'].inputs.prompt, '旅行镜头');
  assert.equal((await client.clipStatus('prompt-1')).status, 'completed');
  assert.throws(() => createComfyClient({ baseUrl: 'http://public.example:8188', workflowPath }), /私网/);
  assert.throws(() => createComfyClient({ baseUrl: 'https://public.example:8188', workflowPath }), /私网/);
});

test('bundled Spark workflow uses native local H3 image-to-video nodes', async () => {
  const workflow = JSON.parse(await readFile(new URL('../workflows/minimax-h3-i2v-api.json', import.meta.url)));
  const classes = Object.values(workflow).map(node => node.class_type);
  assert.ok(classes.includes('MiniMaxH3ImageToVideo'));
  assert.ok(classes.includes('UNETLoader'));
  assert.ok(classes.includes('SaveVideo'));
  assert.equal(workflow['5'].inputs.image, '__TRAVEL_IMAGE__');
  assert.equal(workflow['6'].inputs.prompt, '__TRAVEL_PROMPT__');
  assert.ok(classes.every(name => !/Partner|API/i.test(name)));
});
