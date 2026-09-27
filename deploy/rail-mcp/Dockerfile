FROM docker.1panel.live/library/node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
USER node
EXPOSE 4177
CMD ["/app/node_modules/.bin/12306-mcp", "--host", "0.0.0.0", "--port", "4177"]
