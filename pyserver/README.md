# Python backend modules

`pyserver.app` is the FastAPI composition root. Each feature owns its HTTP routes, state, and integrations in a package:

| Package | Responsibility |
| --- | --- |
| `agent/` | Persistent Step Plan loop, streamed model client, lazy tool catalog, tool dispatch, trip specification, supplier discovery, and itinerary assembly |
| `providers/` | HTTP clients for the Node.js Docker MCP endpoints on Spark, plus the Spark JS transport API and non-MCP place providers |
| `trips/` | Durable trip records, status projection, and trip endpoints |
| `settings/` | YAML configuration, credential and priority schema, and settings endpoints |
| `media/` | Private photo store, image processing (EXIF / normalize / enhance), the photo curation pipeline (L0 quality, burst dedup, VLM tagging), Spark ComfyUI client, persistent jobs, authentication, and media endpoints |
| `api/` | Cross-feature health and capability endpoints, planning stream, and built frontend files |

Photo curation runs in two stages. On upload, `images.extract_exif` pulls capture time, GPS, device, and exposure into metadata while `images.normalize` strips EXIF and caps the long side at 2560. `quality` + `curate` then do the model-free L0 pass — sharpness / exposure / ISO-noise scoring, dHash burst dedup, ordering — and `store.set_quality` writes the scores back. Once a multimodal endpoint is configured, `vlm` overlays semantic tags and a keep-score on the surviving candidates.

The API keeps the existing `/api/*` paths. The Node.js Docker services on Spark host the OTA, 12306, and Dida MCP tools. Python only uses HTTP endpoints: `TRAVEL_OTA_MCP_URL`, `TRAVEL_12306_MCP_URL`, and `TRAVEL_DIDA_MCP_URL` for live `tools/list` discovery; `TRAVEL_DATA_API_URL` for outbound and return transport; `TRAVEL_STAYS_API_URL` for Dida hotels; and `TRAVEL_ATTRACTIONS_API_URL` for OTA attraction products. The Spark JavaScript data service calls its local Docker MCP containers. Python does not build or run those images. Supplier network calls happen only when the matching tool runs, and Spark generation calls happen only after a media job is submitted.

Run locally with `./start.sh`. Run Python tests with `.venv/bin/python -m pytest pyserver/tests -q`.
