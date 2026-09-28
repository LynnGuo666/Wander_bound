# Node MCP adapters

This directory contains supplier normalizers and the data MCP tool handlers. The three raw supplier MCP containers live under `deploy/ota-mcp`, `deploy/rail-mcp`, and `deploy/dida-mcp`; `deploy/travel-data-mcp` packages these normalizers as four high-level read tools. They call suppliers only when the relevant MCP tool is invoked. Credentials arrive per request in private headers, never in tool arguments.

The old Node HTTP server, Agent, settings, and media implementation is preserved in Git at tag `archive/node-server`. The active application backend is `pyserver/`.
