export const STEP_MODEL = 'step-5-preview';
export const STEP_BASE_URL = 'https://api.stepfun.com/v1';

export class ModelCallError extends Error {
  constructor(code, message, retryable = false) {
    super(message);
    this.name = 'ModelCallError';
    this.code = code;
    this.retryable = retryable;
  }
}

const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

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
    async complete(messages, tools, { deadline = Date.now() + 60000 } = {}) {
      if (Date.now() < circuitOpenUntil) throw new ModelCallError('circuit_open', 'StepFun 暂时不可用，等待冷却后重试');
      try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const remaining = deadline - Date.now();
        if (remaining < 1000) throw new ModelCallError('deadline', '模型调用超过规划时限');
        let response;
        try {
          response = await fetchImpl(endpoint, {
            method: 'POST',
            signal: AbortSignal.timeout(Math.min(25000, remaining)),
            headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: STEP_MODEL, messages, tools, temperature: 0.2, max_tokens: 4096, stream: false }),
          });
        } catch (error) {
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
        let payload;
        try { payload = await response.json(); }
        catch { throw new ModelCallError('invalid_json', 'StepFun 返回无效 JSON'); }
        const choice = payload.choices?.[0];
        if (!choice?.message || !['stop', 'tool_calls'].includes(choice.finish_reason)) {
          throw new ModelCallError('invalid_completion', 'StepFun 返回不完整的响应');
        }
        consecutiveFailures = 0;
        return { message: choice.message, finishReason: choice.finish_reason, usage: payload.usage || null };
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
