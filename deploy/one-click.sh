#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE="${1:-auto}" # auto(default=local)|docker|local

STATE_DIR="${HOME}/.auraeve"
ENV_FILE="${PROJECT_DIR}/.env"
ENV_TEMPLATE="${PROJECT_DIR}/.env.docker.example"
CONFIG_FILE="${STATE_DIR}/auraeve.json"
APP_LOG="${SCRIPT_DIR}/app.log"
APP_PID_FILE="${SCRIPT_DIR}/app.pid"

stop_local_app() {
  if [[ -f "${APP_PID_FILE}" ]]; then
    old_pid="$(cat "${APP_PID_FILE}" || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      echo "[one-click] stopping old app: pid=${old_pid}"
      kill "${old_pid}" 2>/dev/null || true
      sleep 1
      if kill -0 "${old_pid}" 2>/dev/null; then
        kill -9 "${old_pid}" 2>/dev/null || true
      fi
    fi
    rm -f "${APP_PID_FILE}"
  fi

  if command -v pgrep >/dev/null 2>&1; then
    mapfile -t stale_pids < <(pgrep -f "${PYTHON_BIN} -m auraeve run" || true)
    if [[ ${#stale_pids[@]} -gt 0 ]]; then
      echo "[one-click] stopping stale app processes: ${stale_pids[*]}"
      kill "${stale_pids[@]}" 2>/dev/null || true
      sleep 1
      kill -9 "${stale_pids[@]}" 2>/dev/null || true
    fi
  fi
}

stop_local_webui_containers() {
  echo "[one-click] stopping previous docker services for clean restart (webui/backend)"
  (cd "${PROJECT_DIR}" && docker compose stop webui backend >/dev/null 2>&1 || true)
  (cd "${PROJECT_DIR}" && docker compose rm -f webui backend >/dev/null 2>&1 || true)
}

mkdir -p "${STATE_DIR}" "${SCRIPT_DIR}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${PROJECT_DIR}/auraeve/config.example.json" "${CONFIG_FILE}"
  echo "[one-click] initialized config: ${CONFIG_FILE}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_TEMPLATE}" "${ENV_FILE}"
  echo "[one-click] initialized env: ${ENV_FILE}"
fi

python - "${CONFIG_FILE}" <<'PY'
from pathlib import Path
import json
import sys
config_path = Path(sys.argv[1])
payload = json.loads(config_path.read_text(encoding="utf-8"))
config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  python3 -m venv "${PROJECT_DIR}/.venv"
fi
"${PYTHON_BIN}" -m pip install -q -r "${PROJECT_DIR}/requirements.txt"

has_docker=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  has_docker=1
fi

if [[ "${MODE}" == "docker" && "${has_docker}" -ne 1 ]]; then
  echo "[one-click] docker mode requested but docker compose is unavailable"
  exit 1
fi

if [[ "${MODE}" == "auto" ]]; then
  MODE="local"
fi

if [[ "${MODE}" == "docker" ]]; then
  echo "[one-click] deploying with docker compose"
  (cd "${PROJECT_DIR}" && docker compose down || true)
  (cd "${PROJECT_DIR}" && docker compose up -d --build)
  echo "[one-click] done"
  echo "  backend: http://127.0.0.1:18080"
  echo "  webui:   http://127.0.0.1:18081"
  exit 0
fi

if [[ "${has_docker}" -ne 1 ]]; then
  echo "[one-click] local mode requires docker for webui container, but docker compose is unavailable"
  exit 1
fi

LOCAL_BACKEND_PORT="${AURAEVE_WEBUI_BIND_PORT:-18780}"

stop_local_app
stop_local_webui_containers

echo "[one-click] starting webui container (proxy -> host.docker.internal:${LOCAL_BACKEND_PORT})"
(cd "${PROJECT_DIR}" && AURAEVE_API_UPSTREAM="host.docker.internal:${LOCAL_BACKEND_PORT}" docker compose up -d --build --no-deps webui)

AURAEVE_WEBUI_BIND_PORT="${LOCAL_BACKEND_PORT}" nohup "${PYTHON_BIN}" -m auraeve run >"${APP_LOG}" 2>&1 &
echo $! > "${APP_PID_FILE}"
echo "[one-click] app started (local mode): pid=$(cat "${APP_PID_FILE}")"
echo "  webui backend bind port: ${LOCAL_BACKEND_PORT}"
