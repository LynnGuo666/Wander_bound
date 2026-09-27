# Python backend modules

`pyserver.app` is the FastAPI composition root. Each feature owns its HTTP routes, state, and integrations in a package:

| Package | Responsibility |
| --- | --- |
| `agent/` | Persistent Step Plan loop, streamed model client, lazy tool catalog, tool dispatch, trip specification, supplier discovery, and itinerary assembly |
| `providers/` | HTTP clients for the Node.js Docker MCP endpoints on Spark, plus the Spark JS transport API and non-MCP place providers |
| `trips/` | Durable trip records, status projection, and trip endpoints |
| `settings/` | YAML configuration, credential and priority schema, and settings endpoints |
| `media/` | Private photo store, image processing, Spark ComfyUI client, persistent jobs, authentication, and media endpoints |
| `api/` | Cross-feature health and capability endpoints, planning stream, and built frontend files |

The API keeps the existing `/api/*` paths. The Node.js Docker services on Spark host the OTA, 12306, and Dida MCP tools. Python only uses HTTP endpoints: `TRAVEL_OTA_MCP_URL` and `TRAVEL_12306_MCP_URL` for capability discovery and places, `TRAVEL_DATA_API_URL` for outbound and return transport, and `TRAVEL_STAYS_API_URL` for Dida hotel results. The Spark JavaScript data service calls its local Docker MCP containers. Python does not build or run those images. Supplier network calls happen only when the model invokes the matching tool, and Spark generation calls happen only after a media job is submitted.

Run locally with `./start.sh`. Run Python tests with `.venv/bin/python -m pytest pyserver/tests -q`.
