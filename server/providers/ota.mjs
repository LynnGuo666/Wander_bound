import { providerAvailability } from './status.mjs';

export async function searchFlyaiTransport(kind, origin, destination, date) {
  if (!origin || !destination) return [];
  const { searchFlyai } = await import('../ota/flyai.mjs');
  return searchFlyai(kind, origin, destination, date);
}

export async function searchTuniuTransport(kind, origin, destination, date) {
  if (!providerAvailability().tuniu.configured || !origin || !destination) return [];
  const { searchTuniu } = await import('../ota/tuniu.mjs');
  return searchTuniu(kind, origin, destination, date);
}

async function searchFlyaiAttractions(city, placeName) {
  const { searchFlyaiAttractions } = await import('../ota/flyai.mjs');
  return searchFlyaiAttractions(city, placeName);
}

async function searchTuniuTickets(placeName, visitDate) {
  const { searchTuniuTickets } = await import('../ota/tuniu.mjs');
  return searchTuniuTickets(placeName, visitDate);
}

export async function searchAttractionProducts(city, places) {
  const targets = places.filter(place => !/公园|广场|街区|海滩|海湾/.test(place.name)).slice(0, 7);
  const jobs = targets.flatMap(place => [
    { place, promise: searchFlyaiAttractions(city, place.name) },
    ...(providerAvailability().tuniu.configured ? [{ place, promise: searchTuniuTickets(place.name, place.visitDate) }] : []),
  ]);
  const responses = await Promise.allSettled(jobs.map(job => job.promise));
  if (jobs.length && responses.every(item => item.status === 'rejected')) throw responses[0].reason;
  const canonical = name => {
    const value = String(name || '').trim();
    return (value.startsWith(city) ? value.slice(city.length) : value).replace(/(?:风景区|景区)$/, '').trim();
  };
  const matched = responses.flatMap((item, index) => item.status === 'fulfilled'
    ? item.value.filter(offer => canonical(offer.name) === canonical(jobs[index].place.name))
      .map(offer => ({ ...offer, placeId: jobs[index].place.id })) : []);
  return [...new Map(matched.map(offer => [`${offer.placeId}:${offer.provider}:${offer.productName}:${offer.price}`, offer])).values()];
}
