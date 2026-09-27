FROM docker.1panel.live/library/node:22-bookworm-slim
WORKDIR /app
COPY server.mjs ./server.mjs
ENV PORT=4178
USER node
EXPOSE 4178
CMD ["node", "server.mjs"]
