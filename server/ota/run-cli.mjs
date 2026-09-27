import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('../../node_modules/.bin/', import.meta.url));
const MAX_OUTPUT = 2_000_000;

export function runCli(binary, args, { timeoutMs = 18000, credentials = {} } = {}) {
  if (!['tuniu', 'flyai'].includes(binary)) throw new Error('未允许的供应商命令');
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (credentials.flyai) env.FLYAI_API_KEY = credentials.flyai;
    if (credentials.tuniu) env.TUNIU_API_KEY = credentials.tuniu;
    const child = spawn(`${BIN}${binary}`, args, { shell: false, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    let finished = false;
    const timeout = setTimeout(() => child.kill('SIGKILL'), timeoutMs);
    function append(current, chunk) {
      const next = current + chunk.toString('utf8');
      if (next.length > MAX_OUTPUT) child.kill('SIGKILL');
      return next.slice(0, MAX_OUTPUT + 1);
    }
    child.stdout.on('data', chunk => { stdout = append(stdout, chunk); });
    child.stderr.on('data', chunk => { stderr = append(stderr, chunk); });
    child.on('error', error => { if (!finished) { finished = true; clearTimeout(timeout); reject(error); } });
    child.on('close', code => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);
      if (code !== 0 || stdout.length > MAX_OUTPUT) return reject(new Error(`${binary} 调用失败（退出码 ${code ?? '超时'}）：${stderr.slice(0, 180)}`));
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error(`${binary} 返回非 JSON 数据`)); }
    });
  });
}
