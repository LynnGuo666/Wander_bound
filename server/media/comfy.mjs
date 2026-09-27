import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export function privateUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw new Error('ComfyUI 服务地址不是有效 URL'); }
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  const tailnet = url.hostname.endsWith('.ts.net');
  if (!['http:', 'https:'].includes(url.protocol) || (!local && !tailnet)
    || url.username || url.password || url.search || url.hash) {
    throw new Error('ComfyUI 只能通过本机回环或 Tailscale 私网连接');
  }
  return url.toString().replace(/\/$/, '');
}

export function fillWorkflow(value, replacements, seen) {
  if (typeof value === 'string') {
    if (Object.hasOwn(replacements, value)) { seen.add(value); return replacements[value]; }
    return value;
  }
  if (Array.isArray(value)) return value.map(item => fillWorkflow(item, replacements, seen));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, fillWorkflow(item, replacements, seen)]));
  return value;
}

export function createComfyClient({
  baseUrl = process.env.SPARK_COMFY_URL || '',
  workflowPath = process.env.SPARK_H3_WORKFLOW_FILE || '',
  fetchImpl = fetch,
} = {}) {
  if (!baseUrl || !workflowPath) return null;
  const root = privateUrl(baseUrl);
  async function request(path, options = {}) {
    const response = await fetchImpl(`${root}${path}`, { ...options, signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(`Spark ComfyUI HTTP ${response.status}`);
    return response;
  }
  return {
    backend: 'dgx-spark-minimax-h3',
    async queueClip(bytes, prompt) {
      const form = new FormData();
      form.append('image', new Blob([bytes], { type: 'image/jpeg' }), `travel-${randomUUID()}.jpg`);
      form.append('overwrite', 'false');
      const upload = await (await request('/upload/image', { method: 'POST', body: form })).json();
      if (!upload.name || !/^[\w. -]{1,160}$/.test(upload.name)) throw new Error('ComfyUI 未返回有效图片名');
      const workflow = JSON.parse(await readFile(workflowPath, 'utf8'));
      const seen = new Set();
      const filled = fillWorkflow(workflow, { __TRAVEL_IMAGE__: upload.name, __TRAVEL_PROMPT__: prompt }, seen);
      if (!seen.has('__TRAVEL_IMAGE__') || !seen.has('__TRAVEL_PROMPT__')) throw new Error('H3 工作流缺少图片或提示词占位符');
      const queued = await (await request('/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: filled, client_id: randomUUID() }) })).json();
      if (!queued.prompt_id || queued.error) throw new Error(`ComfyUI 未接受工作流：${queued.error?.message || '未知原因'}`);
      return queued.prompt_id;
    },
    async clipStatus(promptId) {
      if (!/^[\w-]{1,100}$/.test(promptId)) throw new Error('ComfyUI 任务标识无效');
      const history = await (await request(`/history/${encodeURIComponent(promptId)}`)).json();
      const record = history[promptId];
      if (!record) {
        const queue = await (await request('/queue')).json();
        const pending = [...(queue.queue_running || []), ...(queue.queue_pending || [])]
          .some(item => item[1] === promptId);
        return { status: pending ? 'running' : 'missing' };
      }
      if (record.status?.status_str === 'error' || record.status?.completed === false) return { status: 'failed' };
      const files = Object.values(record.outputs || {}).flatMap(output => [
        ...(output.videos || []), ...(output.gifs || []), ...(output.images || []),
      ]);
      const video = files.find(file => typeof file.filename === 'string' && /\.mp4$/i.test(file.filename));
      if (!video) return { status: record.status?.completed ? 'failed' : 'running' };
      return { status: 'completed', file: video };
    },
    async downloadClip(file) {
      if (!/^[\w. -]{1,180}$/.test(file.filename) || !/\.mp4$/i.test(file.filename)) throw new Error('ComfyUI 输出文件名无效');
      const query = new URLSearchParams({ filename: file.filename, subfolder: file.subfolder || '', type: file.type || 'output' });
      const response = await request(`/view?${query}`);
      const bytes = Buffer.from(await response.arrayBuffer());
      if (!bytes.length || bytes.length > 100 * 1024 * 1024) throw new Error('ComfyUI 视频大小无效');
      return bytes;
    },
  };
}
