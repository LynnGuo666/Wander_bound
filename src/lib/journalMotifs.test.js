import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { hasCurrentJournalAsset, itineraryMotifs, journalPhotoId, pinAutomaticAssets, selectJournalAsset, stickerMotifForItem } from './journalMotifs.js';

const categories = JSON.parse(readFileSync(new URL('../../workflows/journal-sticker-categories.json', import.meta.url), 'utf8'));

test('automatic journal scenes use an actual itinerary landmark', () => {
  const trip = { plan: { destination: '上海', itinerary: [
    { stops: [{ name: '小笼包店' }, { name: '外滩' }] },
  ] } };
  const categories = [{ id: 'food', motif: '{{city}}{{place}}的食物' }];
  const motifs = itineraryMotifs(trip, categories);
  assert.equal(motifs.stickers[0], '上海小笼包店的食物');
  assert.match(motifs.illustration, /上海外滩/);
  assert.match(motifs.postcard, /上海外滩/);
  assert.match(motifs.postcard, /建筑立面局部/);
  assert.match(motifs.stamp, /上海外滩/);
});

test('automatic scenes remain grounded in the city when stops are unavailable', () => {
  const motifs = itineraryMotifs({ plan: { destination: '柳州', itinerary: [] } }, []);
  assert.equal(motifs.illustration, '柳州的建筑、街道与自然光线');
  assert.equal(motifs.postcard, '柳州的一处近景细节');
});

test('sticker themes match relevant stops without repeating city names', () => {
  const trip = { plan: { destination: '上海', itinerary: [
    { stops: [{ name: '上海外滩' }, { name: '小笼包店' }, { name: '上海火车站' }] },
  ] } };
  const chosen = categories.filter(category => ['food', 'architecture', 'transport'].includes(category.id));
  const motifs = itineraryMotifs(trip, chosen);
  assert.match(motifs.stickers[0], /上海小笼包店附近/);
  assert.match(motifs.stickers[1], /上海外滩的代表性建筑/);
  assert.match(motifs.stickers[2], /上海火车站附近/);
  assert.ok(motifs.stickers.every(motif => !motif.includes('上海上海')));
  const cityOnly = itineraryMotifs({ plan: { destination: '柳州', itinerary: [] } }, chosen);
  assert.ok(cityOnly.stickers.every(motif => !motif.includes('柳州柳州')));
  const manualMountain = itineraryMotifs({ plan: { destination: '柳州', itinerary: [] } },
    [categories.find(category => category.id === 'mountain')], { includeAllCategories: true });
  assert.equal(manualMountain.stickers.length, 1);
  assert.ok(manualMountain.stickers[0].startsWith('以柳州为灵感'));
});

test('waterfront postcards request a close detail instead of repeating the landscape', () => {
  const motifs = itineraryMotifs({ plan: { destination: '上海', itinerary: [
    { stops: [{ name: '黄浦江' }] },
  ] } }, []);
  assert.equal(motifs.postcard, '上海黄浦江的水面波纹与光影局部');
  assert.notEqual(motifs.postcard, motifs.illustration);
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

test('outdated Qwen assets are regenerated without blanking an existing system page', () => {
  const versions = { postcard: 'journal-postcard-scene-qwen21-t2i-v4' };
  const old = { id: 'old', kind: 'postcard', motif: '外滩建筑立面', status: 'succeeded',
    promptVersion: 'journal-postcard-scene-qwen21-t2i-v2' };
  const queued = { id: 'queued', kind: 'postcard', motif: old.motif, status: 'queued',
    promptVersion: versions.postcard };
  assert.equal(hasCurrentJournalAsset([old], 'postcard', old.motif, versions), false);
  assert.equal(hasCurrentJournalAsset([queued, old], 'postcard', old.motif, versions), true);
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, '', [queued, old], 'postcard', old.motif)?.id, 'old');
  assert.equal(selectJournalAsset({ source: 'user', protected: true }, 'old', [queued, old], 'postcard', old.motif)?.id, 'old');
  const done = { ...queued, status: 'succeeded' };
  assert.equal(selectJournalAsset({ source: 'system', protected: false }, '', [done, old], 'postcard', old.motif)?.id, 'queued');
});

test('automatic stickers land on different pages and user edits pin all visible media', () => {
  const motifs = { stickers: ['食物', '建筑'], illustration: '城市插画', postcard: '明信片', stamp: '邮票' };
  const system = { source: 'system', protected: false, items: [
    { kind: 'sticker' }, { kind: 'sticker' }, { kind: 'illustration' },
    { kind: 'postcard' }, { kind: 'photo', photoIndex: 1 }, { kind: 'video' },
  ] };
  const jobs = [
    { id: 'food', kind: 'sticker', motif: '食物', status: 'succeeded' },
    { id: 'building', kind: 'sticker', motif: '建筑', status: 'queued' },
    { id: 'scene', kind: 'illustration', motif: '城市插画', status: 'queued' },
    { id: 'card', kind: 'postcard', motif: '明信片', status: 'succeeded' },
    { id: 'stamp', kind: 'stamp', motif: '邮票', status: 'queued' },
  ];
  assert.equal(stickerMotifForItem(system, 0, 0, motifs), '食物');
  assert.equal(stickerMotifForItem(system, 0, 1, motifs), '建筑');
  assert.equal(stickerMotifForItem(system, 1, 0, motifs), '建筑');
  const pinned = pinAutomaticAssets(system, 0, jobs, motifs, ['photo-a', 'photo-b'], ['video-a']);
  assert.deepEqual(pinned.items.map(item => [item.stickerId, item.assetId, item.stampId, item.photoId, item.videoId]), [
    ['food', undefined, undefined, undefined, undefined],
    ['building', undefined, undefined, undefined, undefined],
    [undefined, 'scene', undefined, undefined, undefined],
    [undefined, 'card', 'stamp', undefined, undefined],
    [undefined, undefined, undefined, 'photo-b', undefined],
    [undefined, undefined, undefined, undefined, 'video-a'],
  ]);
  assert.equal(system.items[0].stickerId, undefined);
  const userPage = { ...pinned, source: 'user', protected: true };
  assert.equal(pinAutomaticAssets(userPage, 0, [{ id: 'other', kind: 'sticker', motif: '食物' }], motifs), userPage);
});

test('an early edit keeps its pending Qwen themes and does not switch private photos later', () => {
  const motifs = { stickers: ['外滩建筑'], illustration: '外滩夜色', postcard: '黄浦江', stamp: '上海邮票' };
  const system = { source: 'system', protected: false, items: [
    { kind: 'sticker' }, { kind: 'illustration' }, { kind: 'postcard' }, { kind: 'photo', photoIndex: 0 },
  ] };
  const pinned = pinAutomaticAssets(system, 0, [], motifs);
  assert.equal(pinned.items[0].stickerMotif, '外滩建筑');
  assert.equal(pinned.items[1].assetMotif, '外滩夜色');
  assert.equal(pinned.items[2].assetMotif, '黄浦江');
  assert.equal(pinned.items[2].stampMotif, '上海邮票');
  const userPage = { ...pinned, source: 'user', protected: true };
  const jobs = [{ id: 'new-art', kind: 'sticker', motif: '外滩建筑', status: 'succeeded' }];
  assert.equal(selectJournalAsset(userPage, '', jobs, 'sticker', 'different', pinned.items[0].stickerMotif)?.id, 'new-art');
  assert.equal(selectJournalAsset(userPage, '', jobs, 'sticker', '外滩建筑'), undefined);
  assert.equal(journalPhotoId(userPage, pinned.items[3], ['later-photo']), undefined);
  assert.equal(journalPhotoId(system, system.items[3], ['later-photo']), 'later-photo');
});
