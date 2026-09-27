import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { createComfyClient } from './comfy.mjs';

const run = promisify(execFile);
const UUID = /^[a-f0-9-]{36}$/;

export function createMemoryService({ store, comfy = createComfyClient(), ffmpeg = 'ffmpeg' }) {
  const active = new Map();
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
      const safeTitle = String(title || '').trim().slice(0, 80) || '旅行回忆';
      const clips = [];
      for (const [index, photo] of photos.entries()) {
        const bytes = await store.photoBytes(photo.id);
        const prompt = `旅行回忆短片第 ${index + 1} 个镜头。保留输入照片的主体与真实场景，缓慢平稳的电影感运镜，自然光影。画面里不要出现文字、字幕或标志，不要虚构人物。`;
        clips.push({ photoId: photo.id, promptId: await comfy.queueClip(bytes, prompt) });
      }
      return store.saveJob({ id: randomUUID(), tripId, photoIds, title: safeTitle, backend: comfy.backend,
        status: 'running', clips, createdAt: new Date().toISOString() });
    },
    async get(id) {
      const job = await store.getJob(id);
      if (!job) return null;
      if (job.status !== 'running' || !comfy) return job;
      if (active.has(id)) return job;
      const pending = (async () => {
        let statuses;
        try { statuses = await Promise.all(job.clips.map(clip => comfy.clipStatus(clip.promptId))); }
        catch { return job; }
        if (statuses.some(status => status.status === 'failed')) {
          return store.saveJob({ ...job, status: 'failed', error: '本地视频模型处理失败' });
        }
        if (statuses.some(status => status.status !== 'completed')) return job;
        const directory = path.join(store.root, 'jobs', id);
        await mkdir(directory, { recursive: true, mode: 0o700 });
        const clipPaths = [];
        for (const [index, status] of statuses.entries()) {
          const clipPath = path.join(directory, `${index}.mp4`);
          await writeFile(clipPath, await comfy.downloadClip(status.file), { mode: 0o600 });
          clipPaths.push(clipPath);
        }
        const listPath = path.join(directory, 'clips.txt');
        await writeFile(listPath, clipPaths.map(clipPath => `file '${clipPath.replace(/'/g, "'\\''")}'`).join('\n'), { mode: 0o600 });
        await run(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listPath,
          '-c:v', 'libx264', '-c:a', 'aac', '-movflags', '+faststart', path.join(directory, 'memory.mp4')], { timeout: 180000 });
        return store.saveJob({ ...job, status: 'succeeded', completedAt: new Date().toISOString() });
      })().catch(async error => store.saveJob({ ...job, status: 'failed', error: String(error.message || '视频合成失败').slice(0, 180) }));
      active.set(id, pending);
      void pending.then(() => active.delete(id), () => active.delete(id));
      return job;
    },
    async videoPath(id) {
      const job = await store.getJob(id);
      if (job?.status !== 'succeeded') return null;
      const video = path.join(store.root, 'jobs', id, 'memory.mp4');
      try { return (await stat(video)).isFile() ? video : null; } catch { return null; }
    },
  };
}
