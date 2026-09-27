import { createApiServer } from './http.mjs';
import { createStepClient, STEP_MODEL } from './step-client.mjs';

const port = Number(process.env.PORT || 4174);
const host = process.env.HOST || '127.0.0.1';
const model = createStepClient();
const server = createApiServer({ model });

server.listen(port, host, () => console.log(`Travel Agent API: http://${host}:${port} · ${STEP_MODEL} ${model ? 'enabled' : 'unconfigured'}`));
