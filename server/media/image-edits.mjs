import { randomInt, randomUUID } from 'node:crypto';
import { createQwenImageClient } from './qwen-image.mjs';
import { createMediaJobRunner, waitForMediaResult } from './job-runner.mjs';

const ID = /^[a-f0-9-]{36}$/;

export function createImageEditService({ store, comfy = createQwenImageClient(), runner = createMediaJobRunner({ store }) }) {
  if (comfy) runner.register('image-edit', async (job, save) => {
    let promptId = job.promptId;
    if (!promptId) {
      const bytes = await store.photoBytes(job.photoId);
      if (!bytes) throw new Error('原图文件不存在');
      promptId = await comfy.queueEdit(bytes, job.prompt, job.seed);
      await save({ status: 'running', promptId, startedAt: new Date().toISOString() });
    }
    const file = await waitForMediaResult(id => comfy.editStatus(id), promptId,
      { intervalMs: 3_000, timeoutMs: 15 * 60_000 });
    const variant = `ai-${job.id}`;
    await store.savePhotoVariant(job.photoId, variant, await comfy.downloadImage(file), {
      kind: 'creative-redraw', backend: job.backend, seed: job.seed, prompt: job.prompt,
    });
    await save({ status: 'succeeded', variant, completedAt: new Date().toISOString() });
  });

  return {
    configured: Boolean(comfy),
    async create({ photoId, prompt, seed }) {
      if (!comfy) throw Object.assign(new Error('Spark Qwen 图像编辑尚未配置'), { status: 503 });
      if (!ID.test(photoId || '')) throw Object.assign(new Error('照片 ID 无效'), { status: 400 });
      const text = String(prompt || '').trim();
      if (!text || text.length > 2000) throw Object.assign(new Error('修改指令须为 1 至 2000 字'), { status: 400 });
      if (seed !== undefined && (!Number.isSafeInteger(seed) || seed < 0 || seed > 0xffff_ffff)) {
        throw Object.assign(new Error('随机种子无效'), { status: 400 });
      }
      const photo = await store.getPhoto(photoId);
      if (!photo) throw Object.assign(new Error('照片不存在'), { status: 404 });
      return runner.submit({ id: randomUUID(), kind: 'image-edit', photoId, tripId: photo.tripId,
        prompt: text, seed: seed ?? randomInt(0x1_0000_0000), backend: comfy.backend });
    },
    async get(id) {
      const job = await runner.get(id);
      return job?.kind === 'image-edit' ? job : null;
    },
    async retry(id) {
      const job = await runner.get(id);
      if (job?.kind !== 'image-edit') return null;
      return runner.retry(id, () => ({ promptId: null, startedAt: null }));
    },
  };
}
