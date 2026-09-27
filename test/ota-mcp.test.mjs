import test from 'node:test';
import assert from 'node:assert/strict';
import { callOtaMcp, runCli } from '../server/ota/run-cli.mjs';
import { discoverCapabilities } from '../server/capabilities.mjs';

test('OTA adapter invokes only a named MCP tool and sends per-request key outside the JSON-RPC body', async () => {
  const previous = process.env.TRAVEL_OTA_MCP_URL;
  process.env.TRAVEL_OTA_MCP_URL = 'http://127.0.0.1:4176/mcp';
  try {
    const requests = [];
    const fetchImpl = async (url, request) => {
      requests.push({ url, request });
      return { ok: true, json: async () => ({ jsonrpc: '2.0', id: 1, result: { content: [{ type: 'text', text: '{"status":0,"data":{"itemList":[]}}' }] } }) };
    };
    const result = await callOtaMcp('tools/call', { name: 'flyai_search_flight', arguments: { origin: '上海', destination: '深圳', date: '2026-10-09' } }, { credentials: { flyai: 'private-key' }, fetchImpl });
    assert.equal(result.isError, undefined);
    assert.equal(requests[0].url, 'http://127.0.0.1:4176/mcp');
    assert.equal(requests[0].request.headers['X-FlyAI-Key'], 'private-key');
    assert.equal(requests[0].request.body.includes('private-key'), false);
    await assert.rejects(runCli('sh', ['-c', 'whoami']), /未允许/);
  } finally {
    if (previous === undefined) delete process.env.TRAVEL_OTA_MCP_URL;
    else process.env.TRAVEL_OTA_MCP_URL = previous;
  }
});

test('capability discovery reports live MCP descriptions without inventing authenticated upstream tools', async () => {
  const previous = process.env.TRAVEL_OTA_MCP_URL;
  process.env.TRAVEL_OTA_MCP_URL = 'http://127.0.0.1:4176/mcp';
  try {
    const catalog = await discoverCapabilities({}, {
      availability: () => ({ flyai: { configured: true }, dida: { configured: false } }),
      listOta: async () => [{ name: 'flyai_search_flight', description: 'live wrapper tool', inputSchema: { type: 'object' } }],
      didaDiscovery: async () => ({ kind: 'MCP', discovery: 'authentication_required', tools: [] }),
    });
    assert.equal(catalog.connections.ota.discovery, 'runtime');
    assert.equal(catalog.connections.ota.tools[0].description, 'live wrapper tool');
    assert.deepEqual(catalog.connections.dida.tools, []);
  } finally {
    if (previous === undefined) delete process.env.TRAVEL_OTA_MCP_URL;
    else process.env.TRAVEL_OTA_MCP_URL = previous;
  }
});
