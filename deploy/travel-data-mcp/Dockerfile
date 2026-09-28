FROM docker.1panel.live/library/node:22-bookworm-slim
WORKDIR /app
COPY server ./server
COPY shared ./shared
COPY deploy/travel-data-mcp/server.mjs ./deploy/travel-data-mcp/server.mjs
ENV PORT=4179
USER node
EXPOSE 4179
CMD ["node", "deploy/travel-data-mcp/server.mjs"]
