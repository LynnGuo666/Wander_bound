import test from 'node:test';
import assert from 'node:assert/strict';
import { itineraryMotifs, selectJournalAsset } from './journalMotifs.js';

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

test('automatic Qwen art fills system pages without changing user-owned pages', () => {
  const jobs = [{ id: 'generated', kind: 'postcard', motif: '上海外滩的旅途风景' },
    { id: 'chosen', kind: 'postcard', motif: '用户选择的风景' }];
  const motif = '上海外滩的旅途风景';
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, '', jobs, 'postcard', motif)?.id, 'generated');
  assert.equal(selectJournalAsset({ source: 'user', protected: true }, '', jobs, 'postcard', motif), undefined);
  assert.equal(selectJournalAsset({ source: 'user', protected: true }, 'chosen', jobs, 'postcard', motif)?.id, 'chosen');
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, 'missing', jobs, 'postcard', motif), undefined);
});
