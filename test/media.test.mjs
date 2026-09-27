import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import sharp from 'sharp';
import { createApiServer } from '../server/http.mjs';
import { createComfyClient } from '../server/media/comfy.mjs';
import { createMediaHandler } from '../server/media/routes.mjs';
import { createMediaStore } from '../server/media/store.mjs';

let directory;
let server;
let root;
const token = 'test-media-token';

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), 'travel-media-'));
  const store = createMediaStore(directory);
  server = createApiServer({ mediaHandler: createMediaHandler({ token, store, memory: {
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
