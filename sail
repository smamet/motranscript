#!/usr/bin/env bash
# Start, stop, and inspect the local MoTranscript stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.sail"
WEB_DIR="$ROOT/apps/annotator/web"
API_PORT=8000
WEB_PORT=8010
DB_WAIT_SECONDS=60

cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: ./sail <command> [service]

Commands:
  up, start          Start db, api, web, and worker
  down, stop         Stop the stack
  restart            Stop then start
  status             Show what is running
  logs [service]     Tail logs (api, web, worker, or all)
  backup             Dump MySQL + upload originals into backups/

Services started by `up`:
  db       MySQL via docker compose (port 3307)
  api      FastAPI on http://127.0.0.1:8000 (serves built UI from web/dist)
  web      Vite dev server on http://127.0.0.1:8010 (hot reload)
  worker   Background transcription jobs

`up` rebuilds the frontend and restarts api, web, and worker so code changes apply.
EOF
}

log() { printf '%s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; }

need() {
  command -v "$1" >/dev/null 2>&1 || {
    err "missing dependency: $1"
    exit 1
  }
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    err "docker compose is required"
    exit 1
  fi
}

pid_file() { printf '%s/%s.pid' "$RUN_DIR" "$1"; }
log_file() { printf '%s/%s.log' "$RUN_DIR" "$1"; }

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

service_pid() {
  local file
  file="$(pid_file "$1")"
  [[ -f "$file" ]] || return 1
  cat "$file"
}

service_running() {
  local pid
  pid="$(service_pid "$1" 2>/dev/null || true)"
  pid_alive "$pid"
}

db_running() {
  compose ps --status running --services 2>/dev/null | grep -qx db
}

kill_tree() {
  local pid="$1" sig="${2:-TERM}" child
  while read -r child; do
    [[ -n "$child" ]] && kill_tree "$child" "$sig"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  kill -s "$sig" "$pid" 2>/dev/null || true
}

stop_service() {
  local name="$1" pid file
  file="$(pid_file "$name")"
  pid="$(service_pid "$name" 2>/dev/null || true)"
  if pid_alive "$pid"; then
    kill_tree "$pid" TERM
    for _ in $(seq 1 20); do
      pid_alive "$pid" || break
      sleep 0.1
    done
    pid_alive "$pid" && kill_tree "$pid" KILL
    log "stopped $name (pid $pid)"
  fi
  rm -f "$file"
}

start_service() {
  local name="$1" pid
  shift
  mkdir -p "$RUN_DIR"
  : >"$(log_file "$name")"
  # New session so children survive when the launcher shell exits.
  nohup python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
    "$@" >>"$(log_file "$name")" 2>&1 &
  pid=$!
  echo "$pid" >"$(pid_file "$name")"
  sleep 0.2
  if ! pid_alive "$pid"; then
    err "$name failed to start — see $(log_file "$name")"
    exit 1
  fi
  log "started $name (pid $pid)"
}

ensure_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    log "created .env from .env.example"
  fi
}

ensure_python() {
  need uv
  if [[ ! -d "$ROOT/.venv" ]]; then
    log "installing Python dependencies..."
    uv sync
  fi
}

ensure_node() {
  need npm
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    log "installing frontend dependencies..."
    npm install --prefix "$WEB_DIR"
  fi
}

build_web() {
  log "building frontend (served on api port ${API_PORT})..."
  npm run build --prefix "$WEB_DIR"
}

start_or_restart_service() {
  local name="$1"
  shift
  if service_running "$name"; then
    stop_service "$name"
  fi
  start_service "$name" "$@"
}

wait_for_db() {
  local i
  for i in $(seq 1 "$DB_WAIT_SECONDS"); do
    if compose exec -T db mysqladmin ping -h localhost -umotranscript -pmotranscript --silent >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  err "database did not become ready within ${DB_WAIT_SECONDS}s"
  exit 1
}

cmd_up() {
  need docker
  ensure_env
  ensure_python
  ensure_node

  if db_running; then
    log "db already running"
  else
    log "starting db..."
    compose up -d db
  fi
  wait_for_db
  uv run alembic upgrade head
  build_web

  start_or_restart_service api uv run uvicorn apps.annotator.api.main:app --reload --host 127.0.0.1 --port "$API_PORT"
  start_or_restart_service web npm --prefix "$WEB_DIR" run dev -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort
  start_or_restart_service worker uv run python -m apps.annotator.worker

  log ""
  log "MoTranscript is up"
  log "  editor (dev)  http://127.0.0.1:${WEB_PORT}"
  log "  api + static  http://127.0.0.1:${API_PORT}"
}

cmd_down() {
  stop_service worker
  stop_service web
  stop_service api
  if db_running; then
    compose stop db
    log "stopped db"
  fi
  log "MoTranscript is down"
}

cmd_status() {
  local name pid
  if db_running; then
    log "db      running"
  else
    log "db      stopped"
  fi
  for name in api web worker; do
    pid="$(service_pid "$name" 2>/dev/null || true)"
    if pid_alive "$pid"; then
      case "$name" in
        api) log "api     running  pid $pid  http://127.0.0.1:${API_PORT}" ;;
        web) log "web     running  pid $pid  http://127.0.0.1:${WEB_PORT}" ;;
        *) log "$name  running  pid $pid" ;;
      esac
    else
      printf '%-7s stopped\n' "$name"
    fi
  done
}

cmd_logs() {
  local target="${1:-all}" files=()
  mkdir -p "$RUN_DIR"
  case "$target" in
    all)
      files=("$(log_file api)" "$(log_file web)" "$(log_file worker)")
      ;;
    api | web | worker)
      files=("$(log_file "$target")")
      ;;
    *)
      err "unknown service: $target (api, web, worker, all)"
      exit 1
      ;;
  esac
  touch "${files[@]}"
  tail -n 50 -F "${files[@]}"
}

BACKUP_KEEP_DAYS=14

backup_compose() {
  local file="$1"
  shift
  if [[ -n "$file" ]]; then
    compose -f "$file" "$@"
  else
    compose "$@"
  fi
}

mysql_backup_password() {
  local env_pw=""
  if [[ -f "$ROOT/.env" ]]; then
    env_pw="$(grep -E '^MYSQL_PASSWORD=' "$ROOT/.env" | tail -n1 | cut -d= -f2- || true)"
    env_pw="${env_pw#\"}"
    env_pw="${env_pw%\"}"
    env_pw="${env_pw#\'}"
    env_pw="${env_pw%\'}"
  fi
  printf '%s' "${env_pw:-motranscript}"
}

assert_sql_gz() {
  local path="$1" found
  gzip -t "$path"
  set +o pipefail
  found="$(gzip -dc "$path" | head -c 80000 | grep -c "CREATE TABLE" || true)"
  set -o pipefail
  if [[ "${found:-0}" -lt 1 ]]; then
    err "dump does not look like SQL: $path"
    return 1
  fi
}

cmd_backup() {
  need docker
  local stamp backup_dir db_out db_tmp uploads_out mysql_password compose_file=""
  stamp="$(date +%Y%m%d-%H%M)"
  backup_dir="$ROOT/backups"
  mkdir -p "$backup_dir"

  if [[ -f "$ROOT/docker-compose.prod.yml" ]] \
    && compose -f "$ROOT/docker-compose.prod.yml" ps --status running --services 2>/dev/null | grep -qx db; then
    compose_file="$ROOT/docker-compose.prod.yml"
  fi

  if ! backup_compose "$compose_file" ps --status running --services 2>/dev/null | grep -qx db; then
    err "database is not running — start with ./sail up first"
    exit 1
  fi

  mysql_password="$(mysql_backup_password)"
  db_out="$backup_dir/db-${stamp}.sql.gz"
  db_tmp="${db_out}.partial"
  rm -f "$db_tmp"
  # shellcheck disable=SC2064
  trap "rm -f '$db_tmp'" EXIT
  log "dumping MySQL → $db_out"
  backup_compose "$compose_file" exec -T db \
    env MYSQL_PWD="$mysql_password" \
    mysqldump -umotranscript \
      --single-transaction \
      --no-tablespaces \
      --routines \
      --triggers \
      motranscript | gzip -c >"$db_tmp"
  assert_sql_gz "$db_tmp"
  mv "$db_tmp" "$db_out"
  trap - EXIT
  log "wrote $(du -h "$db_out" | awk '{print $1}')"

  uploads_out="$backup_dir/uploads-${stamp}.tar.gz"
  if [[ -n "$compose_file" ]] && backup_compose "$compose_file" exec -T api sh -c \
    'find /data/uploads -type f -print -quit 2>/dev/null' | grep -q .; then
    log "archiving uploads → $uploads_out"
    backup_compose "$compose_file" exec -T api tar -C /data -czf - uploads >"$uploads_out"
    log "wrote $(du -h "$uploads_out" | awk '{print $1}')"
  elif [[ -z "$compose_file" && -d "$ROOT/data/uploads" ]] \
    && find "$ROOT/data/uploads" -type f -print -quit 2>/dev/null | grep -q .; then
    log "archiving uploads → $uploads_out"
    tar -czf "$uploads_out" -C "$ROOT/data" uploads
    log "wrote $(du -h "$uploads_out" | awk '{print $1}')"
  else
    log "no upload files to archive (YouTube audio is regenerable from source_url)"
  fi

  log "pruning backups older than ${BACKUP_KEEP_DAYS} days"
  find "$backup_dir" -type f \( -name 'db-*.sql.gz' -o -name 'uploads-*.tar.gz' \) \
    -mtime +"$BACKUP_KEEP_DAYS" -delete 2>/dev/null || true
  log "backup done"
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    up | start) cmd_up ;;
    down | stop) cmd_down ;;
    restart) cmd_down; cmd_up ;;
    status) cmd_status ;;
    logs) cmd_logs "${1:-all}" ;;
    backup) cmd_backup ;;
    -h | --help | help) usage ;;
    *)
      err "unknown command: $cmd"
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
