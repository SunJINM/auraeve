#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE="${1:-auto}" # auto|docker|local
APP_PID_FILE="${SCRIPT_DIR}/app.pid"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

has_docker=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  has_docker=1
fi

stop_local_app() {
  if [[ -f "${APP_PID_FILE}" ]]; then
    old_pid="$(cat "${APP_PID_FILE}" || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      echo "[stop] stopping app from pid file: pid=${old_pid}"
      kill "${old_pid}" 2>/dev/null || true
      sleep 1
      kill -9 "${old_pid}" 2>/dev/null || true
    fi
    rm -f "${APP_PID_FILE}"
  fi

  if command -v pgrep >/dev/null 2>&1; then
    mapfile -t stale_pids < <(pgrep -f -- "-m auraeve run" || true)
    if [[ ${#stale_pids[@]} -gt 0 ]]; then
      echo "[stop] stopping local app processes: ${stale_pids[*]}"
      kill "${stale_pids[@]}" 2>/dev/null || true
      sleep 1
      kill -9 "${stale_pids[@]}" 2>/dev/null || true
    fi
  fi
}

stop_docker_services() {
  (
    cd "${PROJECT_DIR}"
    echo "[stop] stopping docker compose services (webui/backend)"
    docker compose stop webui backend >/dev/null 2>&1 || true
    docker compose rm -f webui backend >/dev/null 2>&1 || true
    if [[ -n "$(docker compose ps -q 2>/dev/null || true)" ]]; then
      echo "[stop] docker compose down"
      docker compose down >/dev/null 2>&1 || true
    fi
  )
}

case "${MODE}" in
  auto)
    if [[ "${has_docker}" -eq 1 ]]; then
      stop_docker_services
    fi
    stop_local_app
    echo "[stop] done (auto)"
    ;;
  docker)
    if [[ "${has_docker}" -ne 1 ]]; then
      echo "[stop] docker compose is unavailable"
      exit 1
    fi
    stop_docker_services
    echo "[stop] done (docker)"
    ;;
  local)
    stop_local_app
    echo "[stop] done (local)"
    ;;
  *)
    echo "usage: $0 [auto|docker|local]"
    exit 1
    ;;
esac
