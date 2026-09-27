import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import sharp from 'sharp';
import { createImageEditService } from '../server/media/image-edits.mjs';
import { createMediaJobRunner } from '../server/media/job-runner.mjs';
import { createMemoryService } from '../server/media/memories.mjs';
import { createMediaStore } from '../server/media/store.mjs';

async function fixture(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'travel-media-jobs-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const store = createMediaStore(directory);
  const image = await sharp({ create: { width: 512, height: 384, channels: 3, background: '#607c95' } })
    .jpeg().toBuffer();
  const photo = await store.addPhoto(image, { tripId: 'test-trip' });
  return { store, photo, image };
}

async function waitFor(store, id, status) {
  const deadline = Date.now() + 3_000;
  while (Date.now() < deadline) {
    const job = await store.getJob(id);
    if (job?.status === status) return job;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`任务 ${id} 未达到 ${status}`);
}

test('image and video jobs run in one durable Spark queue without status requests driving work', async t => {
  const { store, photo, image } = await fixture(t);
  const runner = createMediaJobRunner({ store });
  t.after(() => runner.stop());
  const events = [];
  const edits = createImageEditService({ store, runner, comfy: {
    backend: 'fake-qwen',
    async queueEdit() { events.push('qwen-queue'); return 'prompt-image'; },
    async editStatus() { await new Promise(resolve => setTimeout(resolve, 80)); return { status: 'completed', file: { filename: 'out.png' } }; },
    async downloadImage() { events.push('qwen-done'); return image; },
  } });
  const memories = createMemoryService({ store, runner, comfy: {
    backend: 'fake-h3',
    async queueClip() { events.push('h3-queue'); return 'prompt-video'; },
    async clipStatus() { return { status: 'completed', file: { filename: 'clip.mp4' } }; },
    async downloadClip() { return Buffer.from('video'); },
  }, exec: async (_command, args) => writeFile(args.at(-1), Buffer.from('memory')) });
  const edit = await edits.create({ photoId: photo.id, prompt: '画成明信片', seed: 7 });
  const memory = await memories.create({ tripId: 'test-trip', photoIds: [photo.id], title: '旅程' });
  const finishedEdit = await waitFor(store, edit.id, 'succeeded');
  const finishedMemory = await waitFor(store, memory.id, 'succeeded');
  assert.ok(events.indexOf('qwen-done') < events.indexOf('h3-queue'));
  assert.equal(finishedEdit.variant, `ai-${edit.id}`);
  assert.equal(finishedMemory.completedClips, 1);
  assert.equal((await readFile(await memories.videoPath(memory.id))).toString(), 'memory');
});

test('an unfinished image job resumes from its saved Comfy prompt after process restart', async t => {
  const { store, photo, image } = await fixture(t);
  const job = await store.saveJob({ id: '11111111-1111-4111-8111-111111111111', kind: 'image-edit', photoId: photo.id,
    tripId: 'test-trip', prompt: '复古色调', seed: 9, backend: 'fake-qwen', status: 'running', promptId: 'existing-prompt',
    createdAt: new Date().toISOString() });
  const runner = createMediaJobRunner({ store });
  t.after(() => runner.stop());
  let queued = 0;
  createImageEditService({ store, runner, comfy: {
    backend: 'fake-qwen',
    async queueEdit() { queued += 1; return 'unexpected'; },
    async editStatus(id) { assert.equal(id, 'existing-prompt'); return { status: 'completed', file: { filename: 'out.png' } }; },
    async downloadImage() { return image; },
  } });
  await waitFor(store, job.id, 'succeeded');
  assert.equal(queued, 0);
  assert.deepEqual((await store.getPhoto(photo.id)).variants, [`ai-${job.id}`]);
});

test('failed image work can be retried without replacing the original photo or job ID', async t => {
  const { store, photo, image } = await fixture(t);
  const runner = createMediaJobRunner({ store });
  t.after(() => runner.stop());
  let submissions = 0;
  const edits = createImageEditService({ store, runner, comfy: {
    backend: 'fake-qwen',
    async queueEdit() { return `prompt-${++submissions}`; },
    async editStatus(id) { return id === 'prompt-1' ? { status: 'failed' } : { status: 'completed', file: { filename: 'out.png' } }; },
    async downloadImage() { return image; },
  } });
  const job = await edits.create({ photoId: photo.id, prompt: '水彩风格' });
  await waitFor(store, job.id, 'failed');
  const retried = await edits.retry(job.id);
  assert.equal(retried.attempt, 2);
  assert.equal((await waitFor(store, job.id, 'succeeded')).id, job.id);
  assert.equal(submissions, 2);
  assert.deepEqual((await store.getPhoto(photo.id)).variants, [`ai-${job.id}`]);
});
