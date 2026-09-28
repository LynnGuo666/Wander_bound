import test from 'node:test';
import assert from 'node:assert/strict';
import { recalledJournalPages, rememberJournalPages } from './journalPageCache.js';

test('adjacent journal preview preserves every page for the same signed-in session', () => {
  const pages = Array.from({ length: 4 }, (_, index) => ({ templateId: `page-${index}`, items: [{ id: `item-${index}` }] }));
  rememberJournalPages('session-a', 'trip-with-four-pages', pages);
  pages[0].items[0].id = 'changed-after-caching';
  const recalled = recalledJournalPages('session-a', 'trip-with-four-pages');
  assert.equal(recalled.length, 4);
  assert.equal(recalled[0].items[0].id, 'item-0');
  recalled[1].items[0].id = 'changed-after-reading';
  assert.equal(recalledJournalPages('session-a', 'trip-with-four-pages')[1].items[0].id, 'item-1');
  assert.equal(recalledJournalPages('session-b', 'trip-with-four-pages'), null);
});
