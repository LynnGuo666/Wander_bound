export function isoLocal(value) {
  const match = String(value || '').match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
  return match ? `${match[1]}T${match[2]}:00` : null;
}

export function price(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const text = String(value).replace(/[¥￥,\s]/g, '');
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) && number >= 0 ? number : null;
}
