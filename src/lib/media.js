import { apiFetch } from './api.js';
export async function mediaRequest(path, token, options = {}) {
  if (!token) throw new Error('请先登录账号');
  const response = await apiFetch(path, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = result?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || result?.error || `请求失败（${response.status}）`);
  }
  return result;
}

export function tripTitle(trip) {
  return trip?.plan?.destination || (trip?.title?.length > 22 ? '规划中的旅程' : trip?.title) || '未命名旅程';
}

export function cityArtwork(trip) {
  const city = String(trip?.plan?.destination || '').replace(/市$/, '').trim();
  if (city === '深圳') return '/art/shenzhen.webp';
  if (city === '柳州') return '/art/liuzhou.webp';
  return '/art/travel-cover.webp';
}

export function tripDate(trip) {
  const plan = trip?.plan;
  if (trip?.kind === 'history' && trip?.history?.days?.length) {
    const days = trip.history.days;
    return `${days[0].date} — ${days[days.length - 1].date}`;
  }
  return plan?.startDate && plan?.endDate ? `${plan.startDate} — ${plan.endDate}` : '等待确定日期';
}
