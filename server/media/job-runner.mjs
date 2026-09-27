const ACTIVE = new Set(['queued', 'running']);

export async function waitForMediaResult(check, id, { intervalMs, timeoutMs }) {
  const deadline = Date.now() + timeoutMs;
  let consecutiveErrors = 0;
  while (Date.now() < deadline) {
    let result;
    try { result = await check(id); consecutiveErrors = 0; }
    catch (error) {
      if (++consecutiveErrors >= 3) throw error;
      await new Promise(resolve => setTimeout(resolve, intervalMs));
      continue;
    }
    if (result.status === 'completed') return result.file;
    if (result.status === 'failed') throw new Error('ComfyUI 任务执行失败');
    if (result.status === 'missing') throw new Error('ComfyUI 任务记录已丢失，请重试');
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  throw new Error('ComfyUI 任务等待超时');
}

export function createMediaJobRunner({ store, onError = console.error } = {}) {
  const handlers = new Map();
  let working = false;

  async function processNext() {
    if (working) return;
    working = true;
    try {
      while (true) {
        const jobs = await store.listJobs();
        jobs.sort((a, b) => (a.queuedAt || a.createdAt || '').localeCompare(b.queuedAt || b.createdAt || ''));
        const job = jobs.find(item => ACTIVE.has(item.status)
          && handlers.has(item.kind || (item.photoIds ? 'memory' : 'image-edit')));
        if (!job) break;
        const kind = job.kind || (job.photoIds ? 'memory' : 'image-edit');
        let current = job;
        const save = async patch => {
          current = await store.saveJob({ ...current, ...patch });
          return current;
        };
        try { await handlers.get(kind)(job, save); }
        catch (error) {
          await save({ status: 'failed', error: String(error.message || error).slice(0, 180),
            completedAt: new Date().toISOString() });
        }
      }
    } catch (error) { onError(error); }
    finally { working = false; }
  }

  const timer = setInterval(() => { void processNext(); }, 5_000);
  timer.unref();

  return {
    register(kind, handler) {
      handlers.set(kind, handler);
      void processNext();
    },
    async submit(job) {
      const now = new Date().toISOString();
      const saved = await store.saveJob({ ...job, status: 'queued', createdAt: job.createdAt || now, queuedAt: now, attempt: 1 });
      void processNext();
      return saved;
    },
    async get(id) { return store.getJob(id); },
    async retry(id, reset) {
      const job = await store.getJob(id);
      if (!job) return null;
      if (job.status !== 'failed') throw Object.assign(new Error('只能重试失败的任务'), { status: 409 });
      const saved = await store.saveJob({ ...job, ...reset(job), status: 'queued', error: null, completedAt: null,
        queuedAt: new Date().toISOString(), attempt: (job.attempt || 1) + 1 });
      void processNext();
      return saved;
    },
    wake() { void processNext(); },
    stop() { clearInterval(timer); },
  };
}
