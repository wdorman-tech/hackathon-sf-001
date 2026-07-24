#!/usr/bin/env bash
# C3 — one-command boot: backend + supervised listener, both restarting on crash.
#
#   make dev
#
# Ctrl-C stops both. The backend is supervised the same way the listener is,
# because a uvicorn that dies mid-demo is just as silent from the phone's side.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
say()   { echo "[$(stamp)] dev: $*"; }

# C5 — profile discipline. `~/.linq/config.json` holds ONE active profile shared
# by every process on this machine, so `linq profile use seller` in any other
# terminal silently repoints us. Fail loudly here rather than send from the
# wrong number mid-demo.
if ! "$ROOT/scripts/check_profile.sh"; then
  say "profile check failed — fix it before booting (or LINQ_SKIP_PROFILE_CHECK=1 to override)"
  [ "${LINQ_SKIP_PROFILE_CHECK:-}" = "1" ] || exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  say "port ${PORT} is already in use:"
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
  say "kill it first — a stale backend with no Linq key answers /health with linq:false"
  exit 1
fi

pids=()
cleanup() {
  say "shutting down"
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

say "backend  -> http://localhost:${PORT}   (log: ${LOG_DIR}/backend.log)"
(
  cd "$ROOT/closer" || exit 1
  while true; do
    .venv/bin/uvicorn app.main:app --port "$PORT" 2>&1 \
      | while IFS= read -r l; do echo "[$(stamp)] $l"; done \
      | tee -a "$LOG_DIR/backend.log"
    echo "[$(stamp)] backend exited — restarting in 2s" | tee -a "$LOG_DIR/backend.log"
    sleep 2
  done
) &
pids+=($!)

say "listener -> supervised   (log: ${LOG_DIR}/listen.log)"
PORT="$PORT" "$ROOT/scripts/listen.sh" &
pids+=($!)

sleep 2
say "health:"
curl -s "http://localhost:${PORT}/health" 2>/dev/null || say "  (backend still coming up)"
echo
say "running. Ctrl-C to stop both.  make inbound  to check the listener is alive."
wait
