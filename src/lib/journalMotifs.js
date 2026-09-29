const SCENIC_STOP = /江|河|湖|海|山|塔|桥|滩|岛|公园|花园|庭园|街|楼|宫|寺|景|广场|博物馆|美术馆/;
const OPTIONAL_STICKERS = {
  river: /江|河|湖|海|滩|湾|水|港|浦/,
  mountain: /山|峰|岭|峡|谷|高原/,
  museum: /博物馆|美术馆|展馆|展览|艺术馆/,
  cafe: /咖啡|茶馆|下午茶|甜品|面包店/,
};
const CATEGORY_STOPS = {
  food: /餐|饭|面|包|火锅|小吃|美食|茶|咖啡|酒|烤|饺|烧/,
  architecture: /楼|塔|桥|宫|寺|城|博物馆|美术馆|建筑|外滩|古镇|街/,
  scenery: /江|河|湖|海|山|滩|岛|公园|花园|景|园/,
  transport: /车站|机场|码头|地铁|火车|高铁|公交|港/,
  ticket: /车站|机场|码头|火车|高铁|港/,
  flowers: /公园|花园|庭园|植物园|园林/,
  night: /夜|灯|晚/,
  market: /市集|市场|夜市|集市/,
  ...OPTIONAL_STICKERS,
};

export function itineraryMotifs(trip, categories, { includeAllCategories = false } = {}) {
  const city = trip.plan?.destination || trip.title || '旅途';
  const stops = (trip.plan?.itinerary || []).flatMap(day => day.stops || [])
    .map(stop => stop?.name).filter(Boolean);
  const cityBase = city.replace(/市$/, '');
  const placeName = stop => stop?.startsWith(cityBase) ? stop.slice(cityBase.length) : stop || '';
  const landmark = stops.find(stop => SCENIC_STOP.test(stop)) || stops[0] || '';
  const location = landmark ? landmark.startsWith(cityBase) ? landmark : `${city}${placeName(landmark)}` : city;
  const selectedCategories = categories.filter(category => includeAllCategories || !OPTIONAL_STICKERS[category.id]
    || stops.some(stop => OPTIONAL_STICKERS[category.id].test(stop)));
  return {
    stickers: selectedCategories.map(category => {
      const rule = CATEGORY_STOPS[category.id];
      const place = placeName(rule ? stops.find(stop => rule.test(stop)) : landmark);
      return category.motif.replaceAll('{{city}}', city).replaceAll('{{place}}', place);
    }),
    stamp: `${location}的微型风景`,
    illustration: `${location}的建筑、街道与自然光线`,
    postcard: `${location}的旅途风景`,
  };
}

export function selectJournalAsset(page, explicitId, jobs, kind, motif, pinnedMotif = '') {
  if (explicitId) return jobs.find(job => job.id === explicitId);
  const matching = job => job.kind === kind && job.motif === (pinnedMotif || motif);
  if (pinnedMotif) return jobs.find(job => matching(job) && job.status !== 'failed') || jobs.find(matching);
  if (page?.source !== 'system' || page.protected) return undefined;
  return jobs.find(job => matching(job) && job.status !== 'failed') || jobs.find(matching);
}

export function stickerMotifForItem(page, pageIndex, itemIndex, motifs) {
  if (!motifs.stickers.length) return '';
  const stickerIndex = page.items.slice(0, itemIndex).filter(item => item.kind === 'sticker').length;
  return motifs.stickers[(pageIndex + stickerIndex) % motifs.stickers.length];
}

export function journalPhotoId(page, item, selectedPhotoIds) {
  if (item.photoId) return item.photoId;
  if (page?.source !== 'system' || page.protected || !selectedPhotoIds.length) return undefined;
  return selectedPhotoIds[(item.photoIndex || 0) % selectedPhotoIds.length];
}

export function pinAutomaticAssets(page, pageIndex, jobs, motifs, selectedPhotoIds = [], videoIds = []) {
  if (page?.protected) return page;
  let changed = false;
  const items = page.items.map((item, itemIndex) => {
    const references = {};
    if (item.kind === 'sticker' && !item.stickerId) {
      const motif = stickerMotifForItem(page, pageIndex, itemIndex, motifs);
      const job = selectJournalAsset(page, '', jobs, 'sticker', motif);
      if (job && job.status !== 'failed') references.stickerId = job.id;
      else if (page.source === 'system' && motif) references.stickerMotif = motif;
    }
    if (['cover', 'illustration'].includes(item.kind) && !item.assetId) {
      const job = selectJournalAsset(page, '', jobs, 'illustration', motifs.illustration);
      if (job && job.status !== 'failed') references.assetId = job.id;
      else if (page.source === 'system' && motifs.illustration) references.assetMotif = motifs.illustration;
    }
    if (item.kind === 'postcard') {
      if (!item.assetId) {
        const job = selectJournalAsset(page, '', jobs, 'postcard', motifs.postcard);
        if (job && job.status !== 'failed') references.assetId = job.id;
        else if (page.source === 'system' && motifs.postcard) references.assetMotif = motifs.postcard;
      }
      if (!item.stampId) {
        const job = selectJournalAsset(page, '', jobs, 'stamp', motifs.stamp);
        if (job && job.status !== 'failed') references.stampId = job.id;
        else if (page.source === 'system' && motifs.stamp) references.stampMotif = motifs.stamp;
      }
    }
    if (item.kind === 'photo' && !item.photoId && selectedPhotoIds.length)
      references.photoId = selectedPhotoIds[(item.photoIndex || 0) % selectedPhotoIds.length];
    if (item.kind === 'video' && !item.videoId && videoIds.length)
      references.videoId = videoIds[0];
    if (!Object.keys(references).length) return item;
    changed = true;
    return { ...item, ...references };
  });
  return changed ? { ...page, items } : page;
}
