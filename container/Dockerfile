# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# Stage 2: Set up the Python backend
FROM python:3.12-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY server/pyproject.toml ./server/
RUN cd server && uv sync --no-dev --no-install-project

COPY server/ ./server/
RUN cd server && uv sync --no-dev

COPY --from=frontend-build /build/dist ./client/dist

RUN mkdir -p /app/server/data

ENV PORT=5000
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

WORKDIR /app/server
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
