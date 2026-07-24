#!/usr/bin/env bash
# C2 — supervised inbound.
#
# `linq webhooks listen` dying is the single worst failure in this product: it
# is SILENT. No error, no bounce, the number just stops answering and every text
# a judge sends vanishes. So it never runs bare — it runs here, restarted
# forever with backoff, every line timestamped into a log you can tail.
#
#   scripts/listen.sh              # forward to localhost:8000
#   PORT=8010 scripts/listen.sh    # somewhere else
#
# Watch it from the outside with `make inbound` — if seconds_since_last_event
# climbs past 300 during a demo, the listener is dead and this script will
# already be trying to bring it back.
set -uo pipefail

PORT="${PORT:-8000}"
PROFILE="${LINQ_PROFILE:-closer}"
TARGET="http://localhost:${PORT}/webhooks/linq"
LOG_DIR="${LOG_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs}"
LOG="${LOG_DIR}/listen.log"

MIN_BACKOFF=1
MAX_BACKOFF=30
backoff=$MIN_BACKOFF
attempt=0

mkdir -p "$LOG_DIR"

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
say()   { echo "[$(stamp)] $*" | tee -a "$LOG"; }

cleanup() { say "supervisor stopping (signal)"; exit 0; }
trap cleanup INT TERM

command -v linq >/dev/null 2>&1 || {
  say "FATAL: \`linq\` is not on PATH. npm install -g @linqapp/cli@latest (needs Node 22+)"
  exit 127
}

say "supervising: linq webhooks listen --profile ${PROFILE} --forward-to ${TARGET}"
say "log: ${LOG}"

while true; do
  attempt=$((attempt + 1))
  started=$(date +%s)
  say "starting listener (attempt ${attempt})"

  # Unbuffered through the log so a tail shows events as they land, not in 4k
  # chunks. Exit status is the listener's, not tee's — hence PIPESTATUS.
  linq webhooks listen --profile "$PROFILE" --forward-to "$TARGET" 2>&1 \
    | while IFS= read -r line; do echo "[$(stamp)] $line"; done \
    | tee -a "$LOG"
  status=${PIPESTATUS[0]}

  ran=$(( $(date +%s) - started ))
  say "listener exited (status ${status}) after ${ran}s"

  # A listener that survived a while was healthy; treat this as a blip and come
  # straight back. Only rapid flapping — a bad profile, a revoked key — earns
  # the escalating wait.
  if [ "$ran" -ge 60 ]; then
    backoff=$MIN_BACKOFF
  else
    backoff=$(( backoff * 2 ))
    [ "$backoff" -gt "$MAX_BACKOFF" ] && backoff=$MAX_BACKOFF
  fi

  say "restarting in ${backoff}s"
  sleep "$backoff"
done
