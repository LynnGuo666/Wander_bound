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

The API keeps the existing `/api/*` paths. The Node.js Docker services on Spark host and parse the OTA and 12306 MCP tools; Python connects to their HTTP URLs (`TRAVEL_OTA_MCP_URL`, `TRAVEL_12306_MCP_URL`). Outbound and return transport are assembled by the JS API at `TRAVEL_DATA_API_URL`. Python does not build or run the MCP Docker images. Supplier network calls happen only when the model invokes the matching tool, and Spark generation calls happen only after a media job is submitted.

Run locally with `./start.sh`. Run Python tests with `.venv/bin/python -m pytest pyserver/tests -q`.
