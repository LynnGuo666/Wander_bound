const entries = new Map();
const MAX_ENTRIES = 32;
const keyFor = (token, tripId) => `${token}\0${tripId}`;

export function rememberJournalPages(token, tripId, pages) {
  if (!token || !tripId || !Array.isArray(pages)) return;
  const key = keyFor(token, tripId);
  entries.delete(key);
  entries.set(key, structuredClone(pages));
  if (entries.size > MAX_ENTRIES) entries.delete(entries.keys().next().value);
}

export function recalledJournalPages(token, tripId) {
  if (!token || !tripId) return null;
  const key = keyFor(token, tripId);
  const pages = entries.get(key);
  return pages ? structuredClone(pages) : null;
}
