export function dateLabel(iso) {
  if (!iso) return '';
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date(`${iso}T12:00:00`));
}

export function money(amount, currency = 'CNY') {
  if (!Number.isFinite(Number(amount))) return '待查询';
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(amount));
}

export function timeOnly(iso) { return iso ? iso.slice(11, 16) : '--:--'; }
