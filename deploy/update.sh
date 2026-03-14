#!/usr/bin/env bash
set -euo pipefail

# AuraEve update script (v2)
# Usage:
#   bash deploy/update.sh
#   bash deploy/update.sh auto|docker|local

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE="${1:-auto}" # auto(default=local)|docker|local

ENV_FILE="${PROJECT_DIR}/.env"
ENV_TEMPLATE="${PROJECT_DIR}/.env.docker.example"
STATE_DIR="${HOME}/.auraeve"
CONFIG_FILE="${STATE_DIR}/auraeve.json"

VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"

APP_PID_FILE="${SCRIPT_DIR}/app.pid"
APP_LOG="${SCRIPT_DIR}/app.log"

mkdir -p "${STATE_DIR}" "${SCRIPT_DIR}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${PROJECT_DIR}/auraeve/config.example.json" "${CONFIG_FILE}"
  echo "[update] initialized config: ${CONFIG_FILE}"
fi

if [[ ! -f "${ENV_FILE}" && -f "${ENV_TEMPLATE}" ]]; then
  cp "${ENV_TEMPLATE}" "${ENV_FILE}"
  echo "[update] initialized env: ${ENV_FILE}"
fi

sync_runtime_config() {
  python - "${CONFIG_FILE}" <<'PY'
from pathlib import Path
import json
import sys
cfg = Path(sys.argv[1])
payload = json.loads(cfg.read_text(encoding='utf-8'))
cfg.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY
}

setup_python() {
  if [[ ! -x "${VENV_PYTHON}" ]]; then
    python3 -m venv "${PROJECT_DIR}/.venv"
  fi
  "${VENV_PYTHON}" -m pip install -q -r "${PROJECT_DIR}/requirements.txt"
}

start_webui_docker_local() {
  if [[ "${has_docker}" -ne 1 ]]; then
    echo "[update] local mode requires docker for webui container, but docker compose is unavailable"
    exit 1
  fi
  local backend_port="${AURAEVE_WEBUI_BIND_PORT:-18780}"
  echo "[update] starting webui container (proxy -> host.docker.internal:${backend_port})..."
  (cd "${PROJECT_DIR}" && AURAEVE_API_UPSTREAM="host.docker.internal:${backend_port}" docker compose up -d --build --no-deps webui)
}

stop_pid_if_running() {
  local pid_file="$1"
  local name="$2"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}" || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      echo "[update] stopping ${name}: pid=${pid}"
      kill "${pid}" 2>/dev/null || true
      sleep 1
      if kill -0 "${pid}" 2>/dev/null; then
        kill -9 "${pid}" 2>/dev/null || true
      fi
    fi
    rm -f "${pid_file}"
  fi
}

start_app_local() {
  stop_pid_if_running "${APP_PID_FILE}" "app"
  local backend_port="${AURAEVE_WEBUI_BIND_PORT:-18780}"
  AURAEVE_WEBUI_BIND_PORT="${backend_port}" nohup "${VENV_PYTHON}" -m auraeve run >"${APP_LOG}" 2>&1 &
  echo $! > "${APP_PID_FILE}"
  echo "[update] app started: pid=$(cat "${APP_PID_FILE}") (webui backend bind port: ${backend_port})"
}

has_docker=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  has_docker=1
fi

if [[ "${MODE}" != "auto" && "${MODE}" != "docker" && "${MODE}" != "local" ]]; then
  echo "[update] invalid mode: ${MODE} (expected auto|docker|local)"
  exit 1
fi

if [[ "${MODE}" == "docker" && "${has_docker}" -ne 1 ]]; then
  echo "[update] docker mode requested but docker compose is unavailable"
  exit 1
fi

if [[ "${MODE}" == "auto" ]]; then
  MODE="local"
fi

cd "${PROJECT_DIR}"

echo "[update] pulling latest code..."
git pull --rebase

echo "[update] installing dependencies..."
setup_python

sync_runtime_config

if [[ "${MODE}" == "docker" ]]; then
  echo "[update] mode=docker, restarting compose stack..."

  docker compose down || true
  docker compose up -d --build
  echo "[update] docker stack restarted"
  exit 0
fi

echo "[update] mode=local, restarting local services..."
start_webui_docker_local
start_app_local

echo "[update] local services restarted"
