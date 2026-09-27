export const controllerFor = (milliseconds = 9000) => AbortSignal.timeout(milliseconds);

export async function jsonGet(url, timeout = 9000) {
  const response = await fetch(url, { signal: controllerFor(timeout) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
