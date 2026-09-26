# Multi-arch on purpose: the target is an Oracle Ampere A1 (arm64), while
# CI builds on x86_64. `docker buildx` picks the right base and the
# embedding model is pulled for whichever architecture is building.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2-binary and asyncpg both ship their own Postgres client code in
# their wheels, so no system libpq package is needed here. curl is for the
# container healthcheck; nothing else needs a system package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Bake the embedding model into the image.
#
# Two reasons this is a build step and not a first-use download:
#  1. Correctness — a container that silently cannot embed because the
#     Hugging Face CDN was unreachable would look like a working app with
#     a dead search feature. Downloading here fails the build loudly.
#  2. Portability — onnxruntime's availability on aarch64 is the single
#     biggest deployment risk of the A1 migration. Exercising it here means
#     CI fails on a laptop instead of the reindex failing in production.
#
# FASTEMBED_CACHE_PATH puts the cache inside the image so the runtime copy
# is found without re-downloading.
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache
RUN mkdir -p "$FASTEMBED_CACHE_PATH" \
    && python -c "\
from fastembed import TextEmbedding; \
m = TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2'); \
v = next(iter(m.embed(['warmup']))); \
assert len(v) == 384, f'expected 384 dimensions, got {len(v)}'\
" \
    && rm -rf /app/var/storage/*

RUN useradd --create-home --uid 1000 omniscient \
    && mkdir -p /app/var/storage \
    && chown -R omniscient:omniscient /app
USER omniscient

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# A single worker on purpose. The in-memory rate limiter
# (core/rate_limit.py) is per-process, so extra workers would each enforce
# the limit independently and multiply the effective cap. Scale with
# replicas behind a load balancer, not with workers inside one container —
# and move the limiter to Redis first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
