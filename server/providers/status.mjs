export function providerAvailability(credentials = {}) {
  const otaMcp = Boolean(process.env.TRAVEL_OTA_MCP_URL);
  return {
    amap: { configured: Boolean(credentials.amap || process.env.AMAP_WEB_KEY), label: '高德地点与路线' },
    dida: { configured: Boolean(credentials.dida || process.env.DIDA_API_KEY), label: '道旅酒店' },
    duffel: { configured: Boolean(credentials.duffel || process.env.DUFFEL_API_KEY), label: 'Duffel 航班' },
    tuniu: { configured: otaMcp && Boolean(credentials.tuniu || process.env.TUNIU_API_KEY), installed: otaMcp, label: '途牛 · OTA MCP' },
    flyai: { configured: otaMcp, installed: otaMcp, mode: credentials.flyai || process.env.FLYAI_API_KEY ? 'key' : 'trial', label: '飞猪 · OTA MCP' },
    rail12306: { configured: Boolean(process.env.TRAVEL_12306_MCP_URL), label: '12306 MCP（社区）' },
    trip: { configured: false, label: '携程景区合作方接口' },
    reviews: { configured: false, label: '大众点评/美团评论 MCP' },
  };
}
