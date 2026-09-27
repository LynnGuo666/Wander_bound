import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fillWorkflow, privateUrl } from './comfy.mjs';

const FILE = /^[\w. -]{1,180}$/;

export function createQwenImageClient({
  baseUrl = process.env.SPARK_QWEN_COMFY_URL || '',
  workflowPath = process.env.SPARK_QWEN_IMAGE_WORKFLOW_FILE || '',
  fetchImpl = fetch,
} = {}) {
  if (!baseUrl || !workflowPath) return null;
  const root = privateUrl(baseUrl);
  async function request(endpoint, options = {}) {
    const response = await fetchImpl(`${root}${endpoint}`, { ...options, signal: AbortSignal.timeout(30_000) });
    if (!response.ok) throw new Error(`Qwen ComfyUI HTTP ${response.status}`);
    return response;
  }
  return {
    backend: 'dgx-spark-qwen-image-2.1',
    async queueEdit(bytes, prompt, seed) {
      const form = new FormData();
      form.append('image', new Blob([bytes], { type: 'image/jpeg' }), `travel-${randomUUID()}.jpg`);
      form.append('overwrite', 'false');
      const upload = await (await request('/upload/image', { method: 'POST', body: form })).json();
      if (!FILE.test(upload.name || '')) throw new Error('ComfyUI 未返回有效图片名');
      const template = JSON.parse(await readFile(workflowPath, 'utf8'));
      const seen = new Set();
      const workflow = fillWorkflow(template, {
        __TRAVEL_IMAGE__: upload.name,
        __TRAVEL_PROMPT__: /<image1>/i.test(prompt) ? prompt : `<image1> ${prompt}`,
        __TRAVEL_SEED__: seed,
      }, seen);
      if (['__TRAVEL_IMAGE__', '__TRAVEL_PROMPT__', '__TRAVEL_SEED__'].some(key => !seen.has(key))) {
        throw new Error('Qwen 工作流缺少输入占位符');
      }
      const result = await (await request('/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: workflow, client_id: randomUUID() }) })).json();
      if (!result.prompt_id || result.error) throw new Error(`ComfyUI 未接受图像编辑：${result.error?.message || '未知原因'}`);
      return result.prompt_id;
    },
    async editStatus(promptId) {
      if (!/^[\w-]{1,100}$/.test(promptId)) throw new Error('ComfyUI 任务标识无效');
      const history = await (await request(`/history/${encodeURIComponent(promptId)}`)).json();
      const record = history[promptId];
      if (!record) {
        const queue = await (await request('/queue')).json();
        const pending = [...(queue.queue_running || []), ...(queue.queue_pending || [])]
          .some(item => item[1] === promptId);
        return { status: pending ? 'running' : 'missing' };
      }
      if (record.status?.status_str === 'error') return { status: 'failed' };
      const file = Object.values(record.outputs || {}).flatMap(output => output.images || [])
        .find(item => typeof item.filename === 'string' && /\.(png|jpe?g|webp)$/i.test(item.filename));
      if (!file) return { status: record.status?.completed ? 'failed' : 'running' };
      return { status: 'completed', file };
    },
    async downloadImage(file) {
      if (!FILE.test(file?.filename || '') || !/\.(png|jpe?g|webp)$/i.test(file.filename)) {
        throw new Error('ComfyUI 输出图片名无效');
      }
      const query = new URLSearchParams({ filename: file.filename, subfolder: file.subfolder || '', type: file.type || 'output' });
      const bytes = Buffer.from(await (await request(`/view?${query}`)).arrayBuffer());
      if (!bytes.length || bytes.length > 30 * 1024 * 1024) throw new Error('ComfyUI 输出图片大小无效');
      return bytes;
    },
  };
}
