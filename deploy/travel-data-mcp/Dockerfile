FROM docker.1panel.live/library/node:22-bookworm-slim
WORKDIR /app
COPY server/providers.mjs ./server/providers.mjs
COPY server/mcp-data ./server/mcp-data
COPY server/ota ./server/ota
COPY server/providers/dida.mjs server/providers/duffel.mjs server/providers/http-client.mjs server/providers/ota.mjs server/providers/rail12306.mjs server/providers/status.mjs ./server/providers/
COPY deploy/travel-data-mcp/server.mjs ./deploy/travel-data-mcp/server.mjs
ENV PORT=4179
USER node
EXPOSE 4179
CMD ["node", "deploy/travel-data-mcp/server.mjs"]
