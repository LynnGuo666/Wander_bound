const SCENIC_STOP = /江|河|湖|海|山|塔|桥|滩|岛|公园|花园|庭园|街|楼|宫|寺|景|广场|博物馆|美术馆/;

export function itineraryMotifs(trip, categories) {
  const city = trip.plan?.destination || trip.title || '旅途';
  const stops = (trip.plan?.itinerary || []).flatMap(day => day.stops || [])
    .map(stop => stop?.name).filter(Boolean);
  const place = index => stops[index % Math.max(stops.length, 1)] || city;
  const landmark = stops.find(stop => SCENIC_STOP.test(stop)) || place(0);
  const location = landmark.includes(city) ? landmark : `${city}${landmark}`;
  return {
    stickers: categories.slice(0, 5).map((category, index) => category.motif
      .replaceAll('{{city}}', city).replaceAll('{{place}}', place(index))),
    stamp: `${location}的微型风景`,
    illustration: `${location}的建筑、街道与自然光线`,
    postcard: `${location}的旅途风景`,
  };
}

export function selectJournalAsset(page, explicitId, jobs, kind, motif) {
  if (explicitId) return jobs.find(job => job.id === explicitId);
  if (page?.source !== 'system' || page.protected) return undefined;
  return jobs.find(job => job.kind === kind && job.motif === motif);
}
