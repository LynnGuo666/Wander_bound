export function city(value, label = '城市') {
  if (typeof value !== 'string' || !value.trim() || value.length > 100) throw new Error(`${label}无效`);
  return value.trim();
}

export function date(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number.isNaN(Date.parse(`${value}T12:00:00Z`))) throw new Error('日期无效');
  return value;
}

export function days(value) {
  if (!Number.isInteger(value) || value < 1 || value > 21) throw new Error('天数无效');
  return value;
}

export function addDays(value, offset) {
  const result = new Date(`${date(value)}T12:00:00Z`);
  result.setUTCDate(result.getUTCDate() + offset);
  return result.toISOString().slice(0, 10);
}

export function credentialsFromHeaders(headers) {
  const result = {};
  for (const [name, header] of Object.entries({ tuniu: 'x-tuniu-key', dida: 'x-dida-key', flyai: 'x-flyai-key', duffel: 'x-duffel-key' })) {
    const value = headers[header];
    if (value === undefined) continue;
    if (typeof value !== 'string' || !value.trim() || value.length > 512 || /[\x00-\x1f]/.test(value)) throw new Error('凭据格式无效');
    result[name] = value.trim();
  }
  return result;
}
