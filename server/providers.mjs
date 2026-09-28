import { providerAvailability } from './providers/status.mjs';
export { providerAvailability };

// Each MCP call owns its credentials. Never mutate process.env for concurrent users.
export function createRequestProviders(credentials = {}) {
  const key = (name, envName) => credentials[name] || process.env[envName];
  const runner = async (binary, args) => {
    const { runCli } = await import('./ota/run-cli.mjs');
    return runCli(binary, args, { credentials });
  };
  return {
    providerAvailability: () => providerAvailability(credentials),
    searchDidaHotels: async (...args) => key('dida', 'DIDA_API_KEY') ? (await import('./providers/dida.mjs')).searchDidaHotels(...args, key('dida', 'DIDA_API_KEY')) : [],
    searchDuffelFlights: async (...args) => key('duffel', 'DUFFEL_API_KEY') ? (await import('./providers/duffel.mjs')).searchDuffelFlights(...args, key('duffel', 'DUFFEL_API_KEY')) : [],
    searchFlyaiTransport: async (...args) => (await import('./providers/ota.mjs')).searchFlyaiTransport(...args, runner),
    searchTuniuTransport: async (...args) => (await import('./providers/ota.mjs')).searchTuniuTransport(...args, runner, Boolean(key('tuniu', 'TUNIU_API_KEY'))),
    searchAttractionProducts: async (...args) => (await import('./providers/ota.mjs')).searchAttractionProducts(...args, runner, Boolean(key('tuniu', 'TUNIU_API_KEY'))),
    searchRailTickets: async (origin, destination, date) => (await import('./providers/rail12306.mjs')).searchRailTickets(origin, destination, date),
  };
}
