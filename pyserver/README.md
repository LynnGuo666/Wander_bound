# Python backend modules

`pyserver.app` is the FastAPI composition root. Each feature owns its HTTP routes, state, and integrations in a package:

| Package | Responsibility |
| --- | --- |
| `agent/` | Persistent Step Plan loop, streamed model client, lazy tool catalog, tool dispatch, trip specification, supplier discovery, and itinerary assembly |
| `providers/` | MCP JSON RPC transport and independent place and rail adapters |
| `trips/` | Durable trip records, status projection, and trip endpoints |
| `settings/` | YAML configuration, credential and priority schema, and settings endpoints |
| `media/` | Private photo store, image processing, Spark ComfyUI client, persistent jobs, authentication, and media endpoints |
| `api/` | Cross-feature health and capability endpoints, planning stream, and built frontend files |

The API keeps the existing `/api/*` paths. Supplier network calls happen only when the model invokes the matching tool, and Spark generation calls happen only after a media job is submitted.

Run locally with `./start.sh`. Run Python tests with `.venv/bin/python -m pytest pyserver/tests -q`.
