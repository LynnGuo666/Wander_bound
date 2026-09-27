import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { createComfyClient } from './comfy.mjs';
import { createMediaJobRunner, waitForMediaResult } from './job-runner.mjs';

const run = promisify(execFile);
const UUID = /^[a-f0-9-]{36}$/;

export function createMemoryService({ store, comfy = createComfyClient(), ffmpeg = 'ffmpeg',
  runner = createMediaJobRunner({ store }), exec = run }) {
  if (comfy) runner.register('memory', async (job, save) => {
    const directory = path.join(store.root, 'jobs', job.id);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const clips = job.clips?.length ? job.clips : job.photoIds.map(photoId => ({ photoId }));
    const clipPaths = [];
    for (const [index, photoId] of job.photoIds.entries()) {
      const clipPath = path.join(directory, `${index}.mp4`);
      let clip = clips[index] || { photoId };
      if (!clip.promptId) {
        const bytes = await store.photoBytes(photoId);
        if (!bytes) throw new Error('镜头原图文件不存在');
        const prompt = `旅行回忆短片第 ${index + 1} 个镜头。保留输入照片的主体与真实场景，缓慢平稳的电影感运镜，自然光影。画面里不要出现文字、字幕或标志，不要虚构人物。`;
        clip = { ...clip, promptId: await comfy.queueClip(bytes, prompt) };
        clips[index] = clip;
        await save({ status: 'running', clips: [...clips], completedClips: index, startedAt: job.startedAt || new Date().toISOString() });
      }
      if (!clip.done) {
        const file = await waitForMediaResult(id => comfy.clipStatus(id), clip.promptId,
          { intervalMs: 5_000, timeoutMs: 30 * 60_000 });
        await writeFile(clipPath, await comfy.downloadClip(file), { mode: 0o600 });
        clip = { ...clip, done: true };
        clips[index] = clip;
        await save({ status: 'running', clips: [...clips], completedClips: index + 1 });
      }
      clipPaths.push(clipPath);
    }
    const listPath = path.join(directory, 'clips.txt');
    await writeFile(listPath, clipPaths.map(clipPath => `file '${clipPath.replace(/'/g, "'\\''")}'`).join('\n'), { mode: 0o600 });
    await exec(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listPath,
      '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart', path.join(directory, 'memory.mp4')], { timeout: 180000 });
    await save({ status: 'succeeded', completedAt: new Date().toISOString() });
  });

  return {
    configured: Boolean(comfy),
    async create({ tripId, photoIds, title }) {
      if (!comfy) throw Object.assign(new Error('Spark 本地 MiniMax H3 尚未配置'), { status: 503 });
      if (!Array.isArray(photoIds) || photoIds.length < 1 || photoIds.length > 8
        || new Set(photoIds).size !== photoIds.length || photoIds.some(id => !UUID.test(id))) {
        throw Object.assign(new Error('请选择 1 至 8 张不重复的照片'), { status: 400 });
      }
      const photos = await Promise.all(photoIds.map(id => store.getPhoto(id)));
      if (photos.some(photo => !photo || photo.tripId !== tripId)) throw Object.assign(new Error('照片不属于该行程'), { status: 404 });
      return runner.submit({ id: randomUUID(), kind: 'memory', tripId, photoIds,
        title: String(title || '').trim().slice(0, 80) || '旅行回忆', backend: comfy.backend,
        clips: photoIds.map(photoId => ({ photoId })), completedClips: 0 });
    },
    async get(id) {
      const job = await runner.get(id);
      return job?.kind === 'memory' || (job?.photoIds && !job.kind) ? job : null;
    },
    async retry(id) {
      const job = await runner.get(id);
      if (job?.kind !== 'memory' && !(job?.photoIds && !job.kind)) return null;
      return runner.retry(id, current => ({ clips: (current.clips || []).map(clip => clip.done ? clip : {
        photoId: clip.photoId,
      }), startedAt: null }));
    },
    async videoPath(id) {
      const job = await store.getJob(id);
      if (job?.status !== 'succeeded') return null;
      const video = path.join(store.root, 'jobs', id, 'memory.mp4');
      try { return (await stat(video)).isFile() ? video : null; } catch { return null; }
    },
  };
}
