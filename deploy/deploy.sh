#!/usr/bin/env bash
# Deploy / update MoTranscript on the VPS (run from /opt/motranscript as ubuntu).
# Never rsync a laptop .env over this machine — production secrets live only here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.production.example and fill secrets"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

: "${MYSQL_PASSWORD:?MYSQL_PASSWORD required}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD required}"
: "${SECRET_KEY:?SECRET_KEY required}"

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
curl -fsS "http://127.0.0.1:8000/api/health" || true
echo "Deployed."
