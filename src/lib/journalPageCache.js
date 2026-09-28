const entries = new Map();
const MAX_ENTRIES = 32;
const keyFor = (token, tripId) => `${token}\0${tripId}`;

function remember(token, tripId, patch) {
  if (!token || !tripId) return;
  const key = keyFor(token, tripId);
  const previous = entries.get(key) || {};
  entries.delete(key);
  entries.set(key, structuredClone({ ...previous, ...patch }));
  if (entries.size > MAX_ENTRIES) entries.delete(entries.keys().next().value);
}

export function rememberJournalPages(token, tripId, pages) {
  if (Array.isArray(pages)) remember(token, tripId, { pages });
}

export function rememberJournalVisuals(token, tripId, visuals) {
  remember(token, tripId, visuals);
}

export function recalledJournalPages(token, tripId) {
  if (!token || !tripId) return null;
  const pages = entries.get(keyFor(token, tripId))?.pages;
  return pages ? structuredClone(pages) : null;
}

export function recalledJournalVisuals(token, tripId) {
  if (!token || !tripId) return null;
  const entry = entries.get(keyFor(token, tripId));
  if (!entry) return null;
  const { photos, selectedIds, stickers, works } = entry;
  return structuredClone({ photos, selectedIds, stickers, works });
}
