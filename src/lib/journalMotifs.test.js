import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { itineraryMotifs, selectJournalAsset } from './journalMotifs.js';

const categories = JSON.parse(readFileSync(new URL('../../workflows/journal-sticker-categories.json', import.meta.url), 'utf8'));

test('automatic journal scenes use an actual itinerary landmark', () => {
  const trip = { plan: { destination: '上海', itinerary: [
    { stops: [{ name: '小笼包店' }, { name: '外滩' }] },
  ] } };
  const categories = [{ motif: '{{city}}{{place}}的食物' }];
  const motifs = itineraryMotifs(trip, categories);
  assert.equal(motifs.stickers[0], '上海小笼包店的食物');
  assert.match(motifs.illustration, /上海外滩/);
  assert.match(motifs.postcard, /上海外滩/);
  assert.match(motifs.stamp, /上海外滩/);
});

test('automatic scenes remain grounded in the city when stops are unavailable', () => {
  const motifs = itineraryMotifs({ plan: { destination: '柳州', itinerary: [] } }, []);
  assert.equal(motifs.illustration, '柳州的建筑、街道与自然光线');
  assert.equal(motifs.postcard, '柳州的旅途风景');
});

test('a new trip receives twelve varied stickers plus itinerary-relevant extras', () => {
  const ordinary = itineraryMotifs({ plan: { destination: '上海', itinerary: [] } }, categories);
  assert.equal(ordinary.stickers.length, 12);
  assert.ok(ordinary.stickers.some(motif => motif.includes('旅行美食')));
  assert.ok(ordinary.stickers.some(motif => motif.includes('复古相机')));
  assert.ok(ordinary.stickers.every(motif => !motif.includes('山形')));

  const lakesideMuseum = itineraryMotifs({ plan: { destination: '杭州', itinerary: [
    { stops: [{ name: '西湖' }, { name: '浙江省博物馆' }] },
  ] } }, categories);
  assert.equal(lakesideMuseum.stickers.length, 14);
  assert.ok(lakesideMuseum.stickers.some(motif => motif.includes('水岸旅行小景')));
  assert.ok(lakesideMuseum.stickers.some(motif => motif.includes('博物馆收藏')));
});

test('automatic Qwen art fills system pages without changing user-owned pages', () => {
  const jobs = [{ id: 'generated', kind: 'postcard', motif: '上海外滩的旅途风景' },
    { id: 'chosen', kind: 'postcard', motif: '用户选择的风景' }];
  const motif = '上海外滩的旅途风景';
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, '', jobs, 'postcard', motif)?.id, 'generated');
  assert.equal(selectJournalAsset({ source: 'user', protected: true }, '', jobs, 'postcard', motif), undefined);
  assert.equal(selectJournalAsset({ source: 'user', protected: true }, 'chosen', jobs, 'postcard', motif)?.id, 'chosen');
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, 'missing', jobs, 'postcard', motif), undefined);
});
