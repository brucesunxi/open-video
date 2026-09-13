FROM node:22-bookworm-slim AS webbuild
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY web ./web
RUN npm run build && npm prune --omit=dev

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /usr/local/bin/uv
COPY --from=webbuild /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY server ./server
COPY scripts ./scripts
COPY package.json ./
COPY --from=webbuild /app/node_modules ./node_modules
COPY --from=webbuild /app/dist ./dist
ENV DATA_DIR=/data APP_HOST=0.0.0.0 APP_PORT=8010
EXPOSE 8010
CMD ["/app/.venv/bin/python","scripts/start.py"]
