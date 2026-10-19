# syntax=docker/dockerfile:1
# CPU image for VPS: API + ingest worker (no torch/pyannote).

FROM node:22-bookworm AS web
WORKDIR /web
COPY apps/annotator/web/package.json apps/annotator/web/package-lock.json ./
RUN npm ci
COPY apps/annotator/web/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY normalizer ./normalizer
COPY training ./training
COPY alembic ./alembic
COPY alembic.ini ./
COPY --from=web /web/dist ./apps/annotator/web/dist

RUN pip install --upgrade pip \
    && pip install -e .

# Node is needed by yt-dlp for some YouTube challenges
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /data
ENV DATA_DIR=/data \
    MODEL_CACHE_DIR=/data/models \
    INFERENCE_BACKEND=runpod

EXPOSE 8000
CMD ["uvicorn", "apps.annotator.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
