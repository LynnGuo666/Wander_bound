import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createApiServer } from '../server/http.mjs';
import { createConfigStore } from '../server/config.mjs';

let server;
let baseUrl;
let calls = 0;

before(async () => {
  server = createApiServer({
    availability: () => ({ amap: { configured: false } }),
    runAgent: async input => { calls += 1; return { destination: input.destination }; },
    allowedOrigin: 'https://travel.example',
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise(resolve => server.close(resolve));
});

test('health is available and CORS is limited to the configured origin', async () => {
  const untrusted = await fetch(`${baseUrl}/api/health`, { headers: { Origin: 'https://other.example' } });
  assert.equal(untrusted.status, 200);
  assert.equal(untrusted.headers.get('access-control-allow-origin'), null);
  assert.deepEqual((await untrusted.json()).providers, { amap: { configured: false } });

  const trusted = await fetch(`${baseUrl}/api/health`, { headers: { Origin: 'https://travel.example' } });
  assert.equal(trusted.headers.get('access-control-allow-origin'), 'https://travel.example');
  const preflight = await fetch(`${baseUrl}/api/plan`, { method: 'OPTIONS', headers: { Origin: 'https://travel.example' } });
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('access-control-allow-origin'), 'https://travel.example');
});

test('plan accepts a JSON object and rejects invalid request bodies before running the agent', async () => {
  const send = (body, contentType = 'application/json') => fetch(`${baseUrl}/api/plan`, {
    method: 'POST',
    headers: { 'Content-Type': contentType },
    body,
  });
  const initialCalls = calls;
  assert.equal((await send('{}', 'text/plain')).status, 415);
  assert.equal((await send('{')).status, 400);
  assert.equal((await send('[]')).status, 400);
  assert.equal((await send(JSON.stringify({ query: '中'.repeat(90000) }))).status, 413);
  assert.equal(calls, initialCalls);

  const response = await send(JSON.stringify({ destination: '深圳' }));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { destination: '深圳' });
  assert.equal(calls, initialCalls + 1);
});

test('settings API saves keys privately and applies saved priorities to later planning requests', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'travel-http-config-'));
  const configStore = createConfigStore({ filename: path.join(directory, 'config.yml'), env: {} });
  let observed;
  const instance = createApiServer({ configStore, model: null,
    modelFactory: ({ apiKey }) => ({ apiKey }),
    runAgent: async (_request, options) => { observed = options; return { ok: true }; },
  });
  await new Promise(resolve => instance.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${instance.address().port}`;
  try {
    const update = await fetch(`${url}/api/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credentials: { stepfun: 'saved-secret' }, priorities: { trains: ['tuniu', 'rail12306', 'flyai'] } }) });
    assert.equal(update.status, 200);
    assert.ok(!JSON.stringify(await update.json()).includes('saved-secret'));
    const settings = await (await fetch(`${url}/api/settings`)).json();
    assert.equal(settings.credentials.stepfun.stored, true);
    assert.ok(!JSON.stringify(settings).includes('saved-secret'));
    const health = await (await fetch(`${url}/api/health`)).json();
    assert.equal(health.model.configured, true);
    await fetch(`${url}/api/plan`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(observed.model.apiKey, 'saved-secret');
    assert.deepEqual(observed.providerPriority.trains, ['tuniu', 'rail12306', 'flyai']);
  } finally {
    await new Promise(resolve => instance.close(resolve));
    await rm(directory, { recursive: true, force: true });
  }
});
