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

export async function searchDidaHotels(city, area, startDate, stayNights, budget) {
  if (!process.env.DIDA_API_KEY) return [];
  const response = await fetch('https://mcp.rollinggo.cn/mcp', {
    method: 'POST',
    signal: controllerFor(14000),
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${process.env.DIDA_API_KEY}`,
    },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 1, method: 'tools/call',
      params: {
        name: 'searchHotels',
        arguments: {
          originQuery: `${city}${area || ''}附近酒店，每晚不高于${budget}元`,
          place: `${city}${area || ''}`, placeType: area ? '区/县' : '城市',
          checkInParam: { checkInDate: startDate, stayNights },
          size: 12,
        },
      },
    }),
  });
  if (!response.ok) throw new Error(`道旅 HTTP ${response.status}`);
  const payload = unpackMcp(await response.text());
  const items = Array.isArray(payload) ? payload : payload.hotels || payload.data?.hotels || payload.data?.list || payload.list || [];
  return items.map((hotel, index) => {
    const location = hotel.location || hotel.coordinates || {};
    const rawPrice = hotel.totalPrice || hotel.price?.total || hotel.price || hotel.minPrice || hotel.displayPrice;
    const amount = typeof rawPrice === 'object' ? rawPrice.amount || rawPrice.value : rawPrice;
    return {
      id: String(hotel.hotelId || hotel.id || `dida-${index}`), provider: '道旅', name: hotel.hotelName || hotel.name || '未命名酒店',
      address: hotel.address || hotel.hotelAddress || '',
      lat: Number(hotel.latitude || location.lat) || null, lng: Number(hotel.longitude || location.lng) || null,
      displayPrice: Number(amount) || null,
      priceBasis: hotel.totalPrice ? '总价' : '展示价，预订前验价',
      totalPrice: Number(hotel.totalPrice) || null,
      currency: hotel.currency || 'CNY',
      rating: Number(hotel.rating || hotel.score) || null,
      bookingUrl: hotel.bookingUrl || hotel.bookUrl || hotel.url || null,
    };
  });
}
