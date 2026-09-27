export const STEP_MODEL = 'step-5-preview';
export const STEP_BASE_URL = 'https://api.stepfun.com/step_plan/v1';

export function stepChannel(baseUrl = process.env.STEPFUN_BASE_URL || STEP_BASE_URL) {
  try {
    const pathname = new URL(baseUrl).pathname.replace(/\/$/, '');
    if (pathname.endsWith('/step_plan/v1')) return 'step-plan';
    if (pathname.endsWith('/v1')) return 'standard';
  } catch { /* The client reports an invalid endpoint when called. */ }
  return 'custom';
}

export class ModelCallError extends Error {
  constructor(code, message, retryable = false) {
    super(message);
    this.name = 'ModelCallError';
    this.code = code;
    this.retryable = retryable;
  }
}

const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function publicTextFilter(onDelta) {
  let pending = '';
  let hidden = false;
  let emitted = 0;
  const send = value => {
    if (!value || !onDelta || emitted >= 240) return;
    const safe = value.slice(0, 240 - emitted);
    emitted += safe.length;
    onDelta(safe);
  };
  return (chunk, final = false) => {
    pending += chunk;
    while (pending) {
      if (hidden) {
        const end = pending.indexOf('</think>');
        if (end < 0) { pending = final ? '' : pending.slice(-7); break; }
        pending = pending.slice(end + 8);
        hidden = false;
      } else {
        const start = pending.indexOf('<think');
        if (start >= 0) {
          send(pending.slice(0, start));
          const close = pending.indexOf('>', start);
          if (close < 0) { pending = final ? '' : pending.slice(start); break; }
          pending = pending.slice(close + 1);
          hidden = true;
        } else {
          const keep = final ? 0 : 6;
          if (pending.length <= keep) break;
          send(pending.slice(0, pending.length - keep));
          pending = pending.slice(pending.length - keep);
        }
      }
    }
  };
}

function completeJson(payload) {
  const choice = payload.choices?.[0];
  if (!choice?.message || !['stop', 'tool_calls'].includes(choice.finish_reason)) {
    throw new ModelCallError('invalid_completion', 'StepFun 返回不完整的响应');
  }
  return { message: choice.message, finishReason: choice.finish_reason, usage: payload.usage || null };
}

async function completeStream(response, onDelta) {
  const reader = response.body?.getReader?.();
  if (!reader) throw new ModelCallError('invalid_stream', 'StepFun 没有返回可读取的流');
  const decoder = new TextDecoder();
  const filter = publicTextFilter(onDelta);
  const calls = new Map();
  let buffer = '';
  let content = '';
  let finishReason = null;
  let usage = null;
  let bytes = 0;
  const consume = frame => {
    const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!data || data === '[DONE]') return;
    let payload;
    try { payload = JSON.parse(data); }
    catch { throw new ModelCallError('invalid_json', 'StepFun 流包含无效 JSON'); }
    if (payload.error) throw new ModelCallError('stream_error', 'StepFun 流返回错误');
    if (payload.usage) usage = payload.usage;
    for (const choice of payload.choices || []) {
      const delta = choice.delta || {};
      const part = typeof delta.content === 'string' ? delta.content
        : Array.isArray(delta.content) ? delta.content.map(item => item.text || '').join('') : '';
      if (part) { content += part; filter(part); }
      for (const tool of delta.tool_calls || []) {
        const index = Number.isInteger(tool.index) ? tool.index : calls.size;
        const current = calls.get(index) || { id: '', type: 'function', function: { name: '', arguments: '' } };
        if (tool.id) current.id += tool.id;
        if (tool.function?.name) current.function.name += tool.function.name;
        if (tool.function?.arguments) current.function.arguments += tool.function.arguments;
        calls.set(index, current);
      }
      if (choice.finish_reason) finishReason = choice.finish_reason;
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 2 * 1024 * 1024) throw new ModelCallError('stream_too_large', 'StepFun 流超过大小限制');
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        consume(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) consume(buffer);
    filter('', true);
  } finally { reader.releaseLock(); }
  if (!['stop', 'tool_calls'].includes(finishReason)) throw new ModelCallError('invalid_completion', 'StepFun 流未正常完成');
  const toolCalls = [...calls.entries()].sort((a, b) => a[0] - b[0]).map(([, call]) => call);
  return { message: { role: 'assistant', content: content || null, ...(toolCalls.length ? { tool_calls: toolCalls } : {}) }, finishReason, usage };
}

export function createStepClient({
  apiKey = process.env.STEPFUN_API_KEY || process.env.STEP_API_KEY,
  baseUrl = process.env.STEPFUN_BASE_URL || STEP_BASE_URL,
  fetchImpl = fetch,
  sleep = pause,
} = {}) {
  if (!apiKey) return null;
  const endpoint = `${baseUrl.replace(/\/$/, '')}/chat/completions`;
  if (!/^https:\/\//.test(endpoint) && !/^http:\/\/127\.0\.0\.1(?::\d+)?\//.test(endpoint)) {
    throw new Error('StepFun 模型地址必须使用 HTTPS 或本机回环地址');
  }
  let consecutiveFailures = 0;
  let circuitOpenUntil = 0;
  return {
    model: STEP_MODEL,
    backend: 'external-stepfun',
    channel: stepChannel(baseUrl),
    async complete(messages, tools, { deadline = Date.now() + 60000, signal = null, onDelta = null } = {}) {
      if (Date.now() < circuitOpenUntil) throw new ModelCallError('circuit_open', 'StepFun 暂时不可用，等待冷却后重试');
      try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const remaining = deadline - Date.now();
        if (remaining < 1000) throw new ModelCallError('deadline', '模型调用超过规划时限');
        let response;
        try {
          response = await fetchImpl(endpoint, {
            method: 'POST',
            signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(Math.min(120000, remaining))]) : AbortSignal.timeout(Math.min(120000, remaining)),
            headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: STEP_MODEL, messages, tools, temperature: 0.2, max_tokens: 4096, stream: true }),
          });
        } catch (error) {
          if (signal?.aborted) throw error;
          if (attempt < 2 && deadline - Date.now() > 1800) { await sleep(350 * (attempt + 1)); continue; }
          throw new ModelCallError('network', `StepFun 连接失败：${error.name === 'TimeoutError' ? '超时' : '网络错误'}`, true);
        }
        if (!response.ok) {
          const retryable = response.status === 429 || response.status >= 500;
          if (retryable && attempt < 2 && deadline - Date.now() > 1800) {
            const after = Number(response.headers?.get?.('retry-after'));
            await sleep(Number.isFinite(after) && after > 0 ? Math.min(after * 1000, 1500) : 350 * (attempt + 1));
            continue;
          }
          throw new ModelCallError(`http_${response.status}`, `StepFun HTTP ${response.status}`, retryable);
        }
        let completion;
        if (response.body?.getReader && !response.headers?.get?.('content-type')?.includes('application/json')) {
          completion = await completeStream(response, onDelta);
        } else {
          let payload;
          try { payload = await response.json(); }
          catch { throw new ModelCallError('invalid_json', 'StepFun 返回无效 JSON'); }
          completion = completeJson(payload);
          if (completion.message.content && !/<\/?think\b/i.test(completion.message.content)) onDelta?.(completion.message.content.slice(0, 240));
        }
        consecutiveFailures = 0;
        return completion;
      }
      throw new ModelCallError('retry_exhausted', 'StepFun 重试次数已用尽');
      } catch (error) {
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) circuitOpenUntil = Date.now() + 30000;
        throw error;
      }
    },
  };
}
