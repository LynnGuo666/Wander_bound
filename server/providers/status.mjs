export function providerAvailability(credentials = {}) {
  return {
    amap: { configured: Boolean(credentials.amap || process.env.AMAP_WEB_KEY), label: '高德地点与路线' },
    dida: { configured: Boolean(credentials.dida || process.env.DIDA_API_KEY), label: '道旅酒店' },
    duffel: { configured: Boolean(credentials.duffel || process.env.DUFFEL_API_KEY), label: 'Duffel 航班' },
    tuniu: { configured: Boolean(credentials.tuniu || process.env.TUNIU_API_KEY || process.env.TUNIU_USE_OAUTH === '1'), installed: true, label: '途牛 MCP CLI' },
    flyai: { configured: true, installed: true, mode: credentials.flyai || process.env.FLYAI_API_KEY ? 'key' : 'trial', label: '飞猪 FlyAI Skill/CLI' },
    trip: { configured: false, label: '携程景区合作方接口' },
    reviews: { configured: false, label: '大众点评/美团评论 MCP' },
  };
}
