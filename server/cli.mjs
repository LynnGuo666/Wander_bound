import { runTravelAgent } from './agent.mjs';
import { createStepClient } from './step-client.mjs';
import { defaultConfigStore } from './config.mjs';
import { createRequestProviders } from './providers.mjs';

const args = process.argv.slice(2);
const query = args[0];
if (!query || query.startsWith('--')) {
  process.stderr.write('用法：npm run agent:cli -- "我想去深圳玩三天" --origin 上海 --date 2026-10-09 [--require-model]\n');
  process.exit(2);
}

const options = {};
let requireModel = false;
for (let index = 1; index < args.length; index += 1) {
  const flag = args[index];
  if (flag === '--require-model') { requireModel = true; continue; }
  const key = { '--origin': 'originCity', '--date': 'startDate', '--days': 'days', '--destination': 'destination' }[flag];
  if (!key || !args[index + 1]) { process.stderr.write(`未知或缺少参数：${flag}\n`); process.exit(2); }
  options[key] = args[index + 1];
  index += 1;
}

const config = await defaultConfigStore.read();
const model = createStepClient({ apiKey: config.credentials.stepfun || process.env.STEPFUN_API_KEY || process.env.STEP_API_KEY });
if (requireModel && !model) {
  process.stderr.write('StepFun API Key 未配置。请先在 travel-agent/.env 设置 STEPFUN_API_KEY。\n');
  process.exit(2);
}
const result = await runTravelAgent({ query, ...options }, { model, providers: createRequestProviders(config.credentials), providerPriority: config.priorities });
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
if (result.status) process.exitCode = 1;
if (requireModel && result.agentRun?.status !== 'completed') process.exitCode = 1;
