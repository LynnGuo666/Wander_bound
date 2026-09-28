import test from 'node:test';
import assert from 'node:assert/strict';
import { recalledJournalPages, recalledJournalVisuals, rememberJournalPages, rememberJournalVisuals } from './journalPageCache.js';

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

test('turning onto a cached journal retains private images and sticker metadata within its session', () => {
  rememberJournalVisuals('session-a', 'trip-media', {
    photos: [{ id: 'photo-a' }], selectedIds: ['photo-a'],
    stickers: [{ id: 'sticker-a', status: 'succeeded' }], works: [{ id: 'video-a', status: 'succeeded' }],
  });
  rememberJournalPages('session-a', 'trip-media', [{ items: [] }, { items: [] }]);
  const visuals = recalledJournalVisuals('session-a', 'trip-media');
  assert.deepEqual(visuals.selectedIds, ['photo-a']);
  assert.equal(visuals.photos[0].id, 'photo-a');
  assert.equal(visuals.stickers[0].id, 'sticker-a');
  assert.equal(visuals.works[0].id, 'video-a');
  assert.equal(recalledJournalVisuals('session-b', 'trip-media'), null);
});
