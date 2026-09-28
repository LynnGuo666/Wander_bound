export const DEFAULT_MEMORY = {
  homeCity: '',
  transportPreference: 'flight',
  pricePriority: true,
  avoidRedEye: true,
  hotelBrands: ['汉庭', '希尔顿'],
  hotelNightBudget: 550,
  diningBudgetPerPerson: 0,
  cuisinePreferences: [],
  visitedCities: [],
  visitedPlaces: [],
  interests: ['海岸', '艺术', '历史街区'],
};

export function normalizeMemory(value = {}) {
  return {
    ...DEFAULT_MEMORY,
    ...value,
    hotelBrands: Array.isArray(value.hotelBrands) ? value.hotelBrands.filter(Boolean) : DEFAULT_MEMORY.hotelBrands,
    cuisinePreferences: Array.isArray(value.cuisinePreferences) ? value.cuisinePreferences.filter(Boolean) : [],
    visitedCities: Array.isArray(value.visitedCities) ? value.visitedCities : [],
    visitedPlaces: Array.isArray(value.visitedPlaces) ? value.visitedPlaces : [],
    interests: Array.isArray(value.interests) ? value.interests : DEFAULT_MEMORY.interests,
  };
}
