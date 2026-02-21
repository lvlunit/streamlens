# Container

Docker setup files for StreamLens.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build for the StreamLens application |
| `docker-compose.yml` | Kafka + Schema Registry for integration tests |

## Running StreamLens in Docker

Build and run from the project root:

```bash
docker build -f container/Dockerfile -t streamlens .
docker run -p 5000:5000 streamlens
```

Open http://localhost:5000.

### Persisting cluster data

Cluster configuration is stored in `/app/server/data/clusters.json` inside the container. Mount a volume to persist it across restarts:

```bash
docker run -p 5000:5000 -v streamlens-data:/app/server/data streamlens
```

### Environment variables

Pass environment variables with `-e`:

```bash
docker run -p 5000:5000 \
  -e AI_PROVIDER=openai \
  -e OPENAI_API_KEY=sk-... \
  streamlens
```

See the [root README](../README.md) for the full list of supported environment variables.

## Running integration tests

Start Kafka and Schema Registry for integration tests:

```bash
docker compose -f container/docker-compose.yml up -d
cd server && uv run pytest tests/integration -v
docker compose -f container/docker-compose.yml down -v
```

Or use the Makefile from the project root:

```bash
make test-integration
```
