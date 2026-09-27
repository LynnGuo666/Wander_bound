import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createConfigStore } from '../server/config.mjs';

test('settings persist in config.yml with private permissions and never return keys', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'travel-config-'));
  const filename = path.join(directory, 'config.yml');
  const store = createConfigStore({ filename, env: {} });
  try {
    const saved = await store.update({ credentials: { stepfun: 'private-plan-key', tuniu: 'private-tuniu-key' },
      priorities: { trains: ['flyai', 'rail12306', 'tuniu'] } });
    assert.equal(saved.credentials.stepfun.stored, true);
    assert.equal(saved.priorities.trains[0], 'flyai');
    assert.ok(!JSON.stringify(saved).includes('private-plan-key'));
    assert.equal((await stat(filename)).mode & 0o777, 0o600);
    assert.match(await readFile(filename, 'utf8'), /private-plan-key/);
    assert.equal((await store.read()).credentials.stepfun, 'private-plan-key');
    await assert.rejects(store.update({ priorities: { trains: ['flyai', 'flyai', 'tuniu'] } }), /优先级/);
    assert.equal((await store.read()).priorities.trains[1], 'rail12306');
    await store.update({ credentials: { stepfun: null } });
    assert.equal((await store.read()).credentials.stepfun, undefined);
  } finally { await rm(directory, { recursive: true, force: true }); }
});
