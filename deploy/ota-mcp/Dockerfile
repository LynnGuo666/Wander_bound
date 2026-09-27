FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY server.mjs ./server.mjs
ENV PORT=4176
USER node
EXPOSE 4176
CMD ["node", "server.mjs"]
