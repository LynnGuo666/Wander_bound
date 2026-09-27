import { controllerFor } from './http-client.mjs';

function unpackMcp(body) {
  const records = body.trim().startsWith('data:')
    ? body.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).filter(line => line !== '[DONE]')
    : [body];
  for (const record of records.reverse()) {
    try {
      const parsed = JSON.parse(record);
      if (parsed.result?.content) {
        const text = parsed.result.content.find(item => item.type === 'text')?.text;
        try { return JSON.parse(text); } catch { return { raw: text }; }
      }
      return parsed.result || parsed;
    } catch { /* Continue until a valid JSON data record is found. */ }
  }
  throw new Error('酒店服务没有返回可解析的数据');
}

// 响应 schema 于 2026-09-28 用正式 token 实测（searchHotels）：
// { success, code, message, hotelInformationList: [{ hotelId, name, address, latitude, longitude,
//   starRating, price: { hasPrice, currency, lowestPrice, message }, bookingUrl, imageUrl, ... }] }
export function normalizeDidaHotels(items, stayNights = 1) {
  return (Array.isArray(items) ? items : []).map((hotel, index) => {
    const price = hotel.price && typeof hotel.price === 'object' ? hotel.price : {};
    const amount = Number(price.lowestPrice);
    const priced = price.hasPrice === true && Number.isFinite(amount) && amount >= 0;
    return {
      id: String(hotel.hotelId ?? `dida-${index}`),
      provider: '道旅',
      name: String(hotel.name || '未命名酒店'),
      address: String(hotel.address || ''),
      lat: Number(hotel.latitude) || null,
      lng: Number(hotel.longitude) || null,
      starRating: Number(hotel.starRating) || null,
      displayPrice: priced ? amount : null,
      totalPrice: priced ? amount : null,
      priceBasis: priced ? `查询时${stayNights}晚总价，预订前验价` : '未取得价格',
      currency: priced ? String(price.currency || 'CNY') : null,
      rating: Number(hotel.starRating) || null,
      bookingUrl: /^https:\/\//.test(hotel.bookingUrl || '') ? hotel.bookingUrl : null,
      imageUrl: /^https:\/\//.test(hotel.imageUrl || '') ? hotel.imageUrl : null,
    };
  });
}

const didaMcpEndpoint = () => process.env.TRAVEL_DIDA_MCP_URL;

// 本地 Docker 道旅 MCP（deploy/dida-mcp，回环 4178）路径：与 OTA MCP 相同的
// tools/call 结构化调用，凭据按请求经 X-Dida-Key 头传入，容器不保存任何密钥。
async function callDidaMcp(name, args, key) {
  const response = await fetch(didaMcpEndpoint(), {
    method: 'POST',
    signal: controllerFor(14000),
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(key ? { 'X-Dida-Key': key } : {}),
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name, arguments: args } }),
  });
  if (!response.ok) throw new Error(`道旅 MCP HTTP ${response.status}`);
  return unpackMcp(await response.text());
}

async function callUpstreamSearch(args, key) {
  const response = await fetch('https://mcp.rollinggo.cn/mcp', {
    method: 'POST',
    signal: controllerFor(14000),
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(key ? { Authorization: `Bearer ${key}` } : {}),
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'searchHotels', arguments: args } }),
  });
  if (!response.ok) throw new Error(`道旅 HTTP ${response.status}`);
  return unpackMcp(await response.text());
}

export async function searchDidaHotels(city, area, startDate, stayNights, budget, key = process.env.DIDA_API_KEY) {
  if (didaMcpEndpoint()) {
    const payload = await callDidaMcp('dida_search_hotels',
      { city, area: area || '', checkInDate: startDate, stayNights, budget, size: 12 }, key);
    if (payload?.success === false) throw new Error(`道旅查询失败：${String(payload.message || '未知错误').slice(0, 120)}`);
    return normalizeDidaHotels(payload?.hotelInformationList, stayNights);
  }
  if (!key) return [];
  const payload = await callUpstreamSearch({
    originQuery: `${city}${area || ''}附近酒店，每晚不高于${budget}元`,
    place: `${city}${area || ''}`, placeType: area ? '区/县' : '城市',
    checkInParam: { checkInDate: startDate, stayNights },
    size: 12,
  }, key);
  if (payload?.success === false) throw new Error(`道旅查询失败：${String(payload.message || '未知错误').slice(0, 120)}`);
  return normalizeDidaHotels(payload?.hotelInformationList, stayNights);
}
