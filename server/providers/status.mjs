export function providerAvailability(credentials = {}) {
  const otaMcp = Boolean(process.env.TRAVEL_OTA_MCP_URL);
  return {
    dida: { configured: Boolean(credentials.dida || process.env.DIDA_API_KEY), label: '道旅酒店' },
    duffel: { configured: Boolean(credentials.duffel || process.env.DUFFEL_API_KEY), label: 'Duffel 航班' },
    tuniu: { configured: otaMcp && Boolean(credentials.tuniu || process.env.TUNIU_API_KEY), installed: otaMcp, label: '途牛 · OTA MCP' },
    flyai: { configured: otaMcp, installed: otaMcp, mode: credentials.flyai || process.env.FLYAI_API_KEY ? 'key' : 'trial', label: '飞猪 · OTA MCP' },
    rail12306: { configured: Boolean(process.env.TRAVEL_12306_MCP_URL), label: '12306 MCP（社区）' },
  };
}
