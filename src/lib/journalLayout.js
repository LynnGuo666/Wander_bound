const accentPositions = [
  { x: 4, y: 5, w: 18, h: 18, r: -10 }, { x: 77, y: 7, w: 18, h: 18, r: 8 },
  { x: 5, y: 75, w: 18, h: 18, r: 7 }, { x: 76, y: 75, w: 18, h: 18, r: -8 },
  { x: 40, y: 4, w: 17, h: 17, r: 11 }, { x: 39, y: 78, w: 17, h: 17, r: -11 },
];

function overlapArea(left, right) {
  return Math.max(0, Math.min(left.x + left.w, right.x + right.w) - Math.max(left.x, right.x))
    * Math.max(0, Math.min(left.y + left.h, right.y + right.h) - Math.max(left.y, right.y));
}

export function addStickerAccents(items, templateId, pageIndex, stickerIds, createId) {
  const count = stickerIds.length >= 6 ? 2 : stickerIds.length >= 4 ? 1 : 0;
  if (!count) return items;
  const result = [...items];
  const first = (templateId.length + pageIndex * 3) % accentPositions.length;
  const z = Math.max(...items.map(item => item.z || 0)) + 1;
  for (let index = 0; index < count; index++) {
    const candidates = accentPositions.map((position, candidateIndex) => ({ position,
      score: result.reduce((total, item) => total + overlapArea(position, item)
        * (item.kind === 'text' ? 2 : item.kind === 'sticker' ? 3 : 1), 0),
      order: (candidateIndex - first + accentPositions.length) % accentPositions.length,
    })).sort((left, right) => left.score - right.score || left.order - right.order);
    result.push({ ...candidates[0].position, id: createId(), kind: 'sticker',
      stickerId: stickerIds[(2 + pageIndex * count + index) % stickerIds.length], z: z + index });
  }
  return result;
}
