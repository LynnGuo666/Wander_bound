import test from 'node:test';
import assert from 'node:assert/strict';
import { addStickerAccents } from './journalLayout.js';

test('AI places six distinct trip stickers across a spread without replacing template items', () => {
  const motifs = ['food', 'architecture', 'scenery', 'transport', 'market', 'river'];
  const base = [
    { id: 'photo', kind: 'photo', x: 8, y: 9, w: 55, h: 50, z: 2 },
    { id: 'text', kind: 'text', x: 18, y: 70, w: 60, h: 20, z: 3 },
  ];
  let sequence = 0;
  const createId = () => `accent-${++sequence}`;
  const left = addStickerAccents([...base, { id: 'left-sticker', kind: 'sticker', stickerId: motifs[0], x: 65, y: 45, w: 20, h: 20, z: 4 }],
    'photo-wall', 0, motifs, createId);
  const right = addStickerAccents([...base, { id: 'right-sticker', kind: 'sticker', stickerId: motifs[1], x: 65, y: 45, w: 20, h: 20, z: 4 }],
    'city-layers', 1, motifs, createId);
  assert.deepEqual(left.slice(0, base.length), base);
  assert.deepEqual(right.slice(0, base.length), base);
  assert.equal(left.length, 5);
  assert.equal(right.length, 5);
  assert.deepEqual(new Set([...left, ...right].filter(item => item.kind === 'sticker').map(item => item.stickerId)), new Set(motifs));
  for (const accent of [...left.slice(-2), ...right.slice(-2)]) {
    assert.ok(accent.x >= 0 && accent.y >= 0 && accent.x + accent.w <= 100 && accent.y + accent.h <= 100);
  }
});
