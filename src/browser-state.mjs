export function upcomingFriday() {
  const date = new Date();
  date.setDate(date.getDate() + ((5 - date.getDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

export function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}

export const SAMPLE_STATUS = {
  amap: { configured: false, label: '高德地点与路线', result: '未配置' },
  dida: { configured: false, label: '道旅酒店', result: '未配置' },
  duffel: { configured: false, label: 'Duffel 航班', result: '未配置' },
  tuniu: { configured: false, label: '途牛 MCP CLI' },
  flyai: { configured: false, label: '飞猪 FlyAI Skill/CLI' },
  trip: { configured: false, label: '携程景区合作方接口' },
  reviews: { configured: false, label: '大众点评/美团评论 MCP' },
};

