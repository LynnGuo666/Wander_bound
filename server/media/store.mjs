import { randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { analyzePhoto, enhancePhoto, normalizePhoto } from './images.mjs';

const ID = /^[a-f0-9-]{36}$/;
const TRIP = /^[a-zA-Z0-9_-]{1,64}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function createMediaStore(root = process.env.MEDIA_STORAGE_DIR || path.resolve('data/media')) {
  const photoDir = path.join(root, 'photos');
  const metaDir = path.join(root, 'metadata');
  const jobDir = path.join(root, 'jobs');
  const photoPath = (id, variant = 'original') => path.join(photoDir, `${id}${variant === 'original' ? '' : `-${variant}`}.jpg`);
  const metaPath = id => path.join(metaDir, `${id}.json`);
  const jobPath = id => path.join(jobDir, `${id}.json`);
  async function directories() {
    await Promise.all([photoDir, metaDir, jobDir].map(dir => mkdir(dir, { recursive: true, mode: 0o700 })));
  }
  async function getPhoto(id) {
    if (!ID.test(id)) return null;
    try { return JSON.parse(await readFile(metaPath(id), 'utf8')); } catch { return null; }
  }
  async function getJob(id) {
    if (!ID.test(id)) return null;
    try { return JSON.parse(await readFile(jobPath(id), 'utf8')); } catch { return null; }
  }
  return {
    root,
    async addPhoto(bytes, { tripId, capturedDay }) {
      if (!TRIP.test(tripId || '') || (capturedDay && !DAY.test(capturedDay))) {
        throw Object.assign(new Error('行程标识或拍摄日期无效'), { status: 400 });
      }
      const normalized = await normalizePhoto(bytes);
      const analysis = await analyzePhoto(normalized.bytes);
      const photo = { id: randomUUID(), tripId, capturedDay: capturedDay || null,
        width: normalized.width, height: normalized.height, analysis, variants: [], createdAt: new Date().toISOString() };
      await directories();
      await writeFile(photoPath(photo.id), normalized.bytes, { mode: 0o600, flag: 'wx' });
      await writeFile(metaPath(photo.id), JSON.stringify(photo), { mode: 0o600, flag: 'wx' });
      return photo;
    },
    getPhoto,
    async listPhotos(tripId) {
      if (!TRIP.test(tripId || '')) throw Object.assign(new Error('行程标识无效'), { status: 400 });
      await directories();
      const names = (await readdir(metaDir)).filter(name => name.endsWith('.json'));
      const photos = await Promise.all(names.map(name => getPhoto(name.slice(0, -5))));
      return photos.filter(photo => photo?.tripId === tripId).sort((a, b) => (a.capturedDay || '').localeCompare(b.capturedDay || ''));
    },
    async photoBytes(id, variant = 'original') {
      const photo = await getPhoto(id);
      if (!photo || (variant !== 'original' && !photo.variants.includes(variant))) return null;
      try { return await readFile(photoPath(id, variant)); } catch { return null; }
    },
    async enhance(id, preset) {
      const photo = await getPhoto(id);
      if (!photo) return null;
      const original = await readFile(photoPath(id));
      const bytes = await enhancePhoto(original, preset);
      await writeFile(photoPath(id, preset), bytes, { mode: 0o600 });
      const updated = { ...photo, variants: [...new Set([...photo.variants, preset])] };
      await writeFile(metaPath(id), JSON.stringify(updated), { mode: 0o600 });
      return updated;
    },
    async saveJob(job) {
      await directories();
      await writeFile(jobPath(job.id), JSON.stringify(job), { mode: 0o600 });
      return job;
    },
    getJob,
    jobPath,
  };
}
