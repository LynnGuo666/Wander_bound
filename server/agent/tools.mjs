import { toolError } from './definitions.mjs';

const loaders = {
  set_trip_spec: () => import('./tool-handlers/basic.mjs').then(module => module.setTripSpec),
  resolve_origin: () => import('./tool-handlers/basic.mjs').then(module => module.resolveOrigin),
  discover_places: () => import('./tool-handlers/basic.mjs').then(module => module.discoverPlaces),
  search_transport: () => import('./tool-handlers/transport.mjs').then(module => module.searchTransport),
  search_stays: () => import('./tool-handlers/stays.mjs').then(module => module.searchStays),
  draft_plan: () => import('./tool-handlers/draft.mjs').then(module => module.draftPlan),
  search_attractions: () => import('./tool-handlers/enrichment.mjs').then(module => module.searchAttractions),
  search_dining: () => import('./tool-handlers/enrichment.mjs').then(module => module.searchDining),
  explore_ground: () => import('./tool-handlers/enrichment.mjs').then(module => module.exploreGround),
};

export function createToolExecutor(context) {
  const cache = new Map();
  return async (name, args = {}, internal = false) => {
    const started = Date.now();
    if (Date.now() >= context.deadline) return toolError('deadline', '规划超时');
    if (name !== 'draft_plan' && name !== 'set_trip_spec' && cache.has(name)) return cache.get(name);
    context.onEvent?.({ type: 'tool_start', tool: name, source: internal ? 'agent' : 'model' });
    let result;
    try {
      const handler = loaders[name] ? await loaders[name]() : null;
      result = handler ? await handler({ ...context, cache, internal }, args) : toolError('unknown_tool', '未知工具');
    } catch (error) {
      result = toolError('tool_failed', error.message || '工具执行失败');
      context.warnings.push(`${name} 执行失败`);
    }
    const entry = { tool: name, ok: result.ok === true, code: result.ok ? 'ok' : String(result.code || 'failed'), durationMs: Date.now() - started };
    context.trace.push(entry);
    context.onEvent?.({ type: 'tool_end', ...entry });
    if (name !== 'draft_plan' && name !== 'set_trip_spec' && (result.ok || result.code === 'no_new_places')) cache.set(name, result);
    return result;
  };
}
