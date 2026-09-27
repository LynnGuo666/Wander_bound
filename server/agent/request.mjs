import { normalizeMemory } from '../../shared/planner.mjs';

function localIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function nextFriday(now) {
  const date = new Date(now);
  date.setDate(date.getDate() + ((5 - date.getDay() + 7) % 7 || 7));
  return localIsoDate(date);
}

export function addDays(iso, days) {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function cleanCity(value) { return String(value || '').trim().replace(/市$/, '').slice(0, 32); }
export function cleanInterests(value) { return Array.isArray(value) ? value.filter(item => typeof item === 'string').map(item => item.slice(0, 24)).slice(0, 10) : []; }

export function safeMemory(raw) {
  const memory = normalizeMemory(raw);
  return {
    ...memory,
    homeCity: cleanCity(memory.homeCity),
    hotelBrands: memory.hotelBrands.filter(item => typeof item === 'string').map(item => item.slice(0, 32)).slice(0, 12),
    visitedCities: memory.visitedCities.filter(item => typeof item === 'string').map(cleanCity).slice(0, 100),
    visitedPlaces: memory.visitedPlaces.filter(item => item && typeof item === 'object')
      .map(item => ({ id: String(item.id || '').slice(0, 80), name: String(item.name || '').slice(0, 80), city: cleanCity(item.city) })).slice(0, 300),
    interests: cleanInterests(memory.interests),
    hotelNightBudget: Math.max(0, Math.min(100000, Number(memory.hotelNightBudget) || 0)),
    diningBudgetPerPerson: Math.max(0, Math.min(10000, Number(memory.diningBudgetPerPerson) || 0)),
    cuisinePreferences: cleanInterests(memory.cuisinePreferences),
  };
}
