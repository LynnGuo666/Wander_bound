import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApiServer } from '../server/http.mjs';

test('debug stream reports live events and keeps per-request keys out of the agent input and trace', async () => {
  const secret = 'step-secret-for-test';
  let received;
  const server = createApiServer({
    modelFactory: ({ apiKey }) => { assert.equal(apiKey, secret); return { backend: 'test' }; },
    runAgent: async (input, options) => {
      received = { input, options };
      options.onEvent({ sequence: 1, type: 'run_start', mode: 'model' });
      options.onEvent({ sequence: 2, type: 'tool_end', tool: 'discover_places', ok: true, durationMs: 4 });
      return { destination: input.destination, agentRun: { status: 'completed' } };
    },
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/plan/stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination: '深圳', credentials: { stepfun: secret, amap: 'amap-test' } }),
    });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /text\/event-stream/);
    const body = await response.text();
    assert.match(body, /event: progress/);
    assert.match(body, /event: result/);
    assert.doesNotMatch(body, /step-secret-for-test|amap-test/);
    assert.equal(received.input.credentials, undefined);
    assert.equal(received.options.providers.providerAvailability().amap.configured, true);
    assert.equal(received.options.model.backend, 'test');
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('invalid credential values are rejected before Agent execution', async () => {
  let called = false;
  const server = createApiServer({ runAgent: async () => { called = true; return {}; } });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/plan`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credentials: { stepfun: 'bad\nkey' } }),
    });
    assert.equal(response.status, 400);
    assert.equal(called, false);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
