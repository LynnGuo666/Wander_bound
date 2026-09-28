import { runCli } from '../ota/run-cli.mjs';
import { city } from './validation.mjs';

export async function searchPlaces(input, credentials = {}, runner = runCli) {
  const name = city(input.city);
  const payload = await runner('flyai', ['search-poi', '--city-name', name], { credentials });
  if (payload?.status !== 0) throw new Error(String(payload?.message || '飞猪地点查询失败'));
  const places = (payload?.data?.itemList || []).flatMap(row => {
    const lat = Number(row.latitude), lng = Number(row.longitude);
    if (!row.id || !row.name || !Number.isFinite(lat) || !Number.isFinite(lng)) return [];
    return [{ id: `flyai-${row.id}`, name: String(row.name), lat, lng, area: name,
      category: String(row.category || '景点'), duration: null, description: String(row.address || ''), source: '飞猪 FlyAI' }];
  });
  return { ok: true, places, source: '飞猪 Docker MCP' };
}
