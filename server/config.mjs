import { readFile, rename, rm, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';

export const CONFIG_PATH = fileURLToPath(new URL('../config.yml', import.meta.url));
export const KEY_ENV = Object.freeze({
  stepfun: 'STEPFUN_API_KEY', amap: 'AMAP_WEB_KEY', dida: 'DIDA_API_KEY',
  duffel: 'DUFFEL_API_KEY', tuniu: 'TUNIU_API_KEY', flyai: 'FLYAI_API_KEY',
});
export const PRIORITY_OPTIONS = Object.freeze({
  flights: ['duffel', 'flyai', 'tuniu'],
  trains: ['rail12306', 'flyai', 'tuniu'],
  attractions: ['flyai', 'tuniu'],
});

const invalid = message => Object.assign(new Error(message), { status: 400 });
const defaults = () => ({ credentials: {}, priorities: Object.fromEntries(Object.entries(PRIORITY_OPTIONS).map(([name, ids]) => [name, [...ids]])) });

function normalize(raw) {
  if (raw == null) return defaults();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw invalid('config.yml 格式无效');
  const result = defaults();
  if (raw.credentials != null) {
    if (!raw.credentials || typeof raw.credentials !== 'object' || Array.isArray(raw.credentials)) throw invalid('config.yml 密钥格式无效');
    for (const name of Object.keys(KEY_ENV)) {
      const value = raw.credentials[name];
      if (value == null || value === '') continue;
      if (typeof value !== 'string' || value.length > 512 || /[\r\n\x00-\x1f]/.test(value)) throw invalid('config.yml 密钥格式无效');
      result.credentials[name] = value;
    }
  }
  if (raw.priorities != null) {
    if (!raw.priorities || typeof raw.priorities !== 'object' || Array.isArray(raw.priorities)) throw invalid('config.yml 优先级格式无效');
    for (const [name, ids] of Object.entries(PRIORITY_OPTIONS)) {
      if (raw.priorities[name] == null) continue;
      const order = raw.priorities[name];
      if (!Array.isArray(order) || order.length !== ids.length || new Set(order).size !== ids.length || order.some(id => !ids.includes(id))) {
        throw invalid(`${name} 优先级必须包含每个可用来源且不重复`);
      }
      result.priorities[name] = [...order];
    }
  }
  return result;
}

export function publicConfig(config, env = process.env) {
  return {
    file: 'config.yml',
    credentials: Object.fromEntries(Object.entries(KEY_ENV).map(([name, envName]) => [name, {
      stored: Boolean(config.credentials[name]),
      environment: Boolean(env[envName] || (name === 'stepfun' && env.STEP_API_KEY)),
      configured: Boolean(config.credentials[name] || env[envName] || (name === 'stepfun' && env.STEP_API_KEY)),
    }])),
    priorities: config.priorities,
    priorityOptions: PRIORITY_OPTIONS,
  };
}

export function mergeConfig(current, patch) {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw invalid('设置请求必须是对象');
  const next = normalize(current);
  if (patch.credentials !== undefined) {
    if (!patch.credentials || typeof patch.credentials !== 'object' || Array.isArray(patch.credentials)) throw invalid('密钥格式无效');
    for (const [name, value] of Object.entries(patch.credentials)) {
      if (!Object.hasOwn(KEY_ENV, name)) throw invalid('未知密钥类型');
      if (value === null) delete next.credentials[name];
      else if (value !== '') {
        if (typeof value !== 'string' || value.length > 512 || /[\r\n\x00-\x1f]/.test(value)) throw invalid('密钥格式无效');
        next.credentials[name] = value.trim();
      }
    }
  }
  if (patch.priorities !== undefined) {
    if (!patch.priorities || typeof patch.priorities !== 'object' || Array.isArray(patch.priorities)) throw invalid('优先级格式无效');
    for (const name of Object.keys(patch.priorities)) if (!Object.hasOwn(PRIORITY_OPTIONS, name)) throw invalid('未知优先级类型');
    return normalize({ ...next, priorities: { ...next.priorities, ...patch.priorities } });
  }
  return next;
}

export function createConfigStore({ filename = process.env.TRAVEL_CONFIG_PATH || CONFIG_PATH, env = process.env } = {}) {
  let writing = Promise.resolve();
  async function read() {
    try { return normalize(YAML.parse(await readFile(filename, 'utf8'), { uniqueKeys: true })); }
    catch (error) {
      if (error.code === 'ENOENT') return defaults();
      if (error.status) throw error;
      throw Object.assign(new Error('无法读取 config.yml'), { status: 500 });
    }
  }
  async function update(patch) {
    const operation = writing.then(async () => {
      const next = mergeConfig(await read(), patch);
      const temporary = `${filename}.${randomUUID()}.tmp`;
      try {
        await writeFile(temporary, YAML.stringify(next), { mode: 0o600, flag: 'wx' });
        await rename(temporary, filename);
      } finally { await rm(temporary, { force: true }); }
      return publicConfig(next, env);
    });
    writing = operation.catch(() => {});
    return operation;
  }
  return { read, update, public: async () => publicConfig(await read(), env) };
}

export const defaultConfigStore = createConfigStore();
