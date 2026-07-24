#!/usr/bin/env bash
# C2/C3 — prove the whole inbound path before a judge does.
#
#   make preflight
#
# Six checks, cheapest first, each one a thing that has actually broken:
#   1. backend up            — nothing else can pass if it isn't
#   2. keys configured       — a stale process reports linq:false and looks fine
#   3. store is durable      — MemoryStore means a restart eats the demo
#   4. listener alive        — the silent killer (C2)
#   5. linq profile correct  — wrong profile = texts from the seller's number (C5)
#   6. round trip            — send a real text and watch the counter move
#
# 1-5 need nothing. 6 needs PREFLIGHT_TO set to a phone that has already texted
# +12052611117 (Shared Line is inbound-first) and is skipped without it.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
BASE="http://localhost:${PORT}"
PROFILE="${LINQ_PROFILE:-closer}"
TO="${PREFLIGHT_TO:-}"

pass=0; fail=0; skip=0
ok()   { echo "  ✅ $*"; pass=$((pass+1)); }
bad()  { echo "  ❌ $*"; fail=$((fail+1)); }
warn() { echo "  ⏭  $*"; skip=$((skip+1)); }

jqr() { # jqr <json> <filter> — jq if present, python otherwise
  if command -v jq >/dev/null 2>&1; then printf '%s' "$1" | jq -r "$2"
  else printf '%s' "$1" | "$ROOT/closer/.venv/bin/python" -c \
    "import json,sys;d=json.load(sys.stdin);print(d.get('${2#.}',''))"; fi
}

echo "preflight -> ${BASE}  (profile ${PROFILE})"
echo

echo "1. backend"
health="$(curl -fsS --max-time 5 "${BASE}/health" 2>/dev/null)" \
  && ok "up" || { bad "no answer on ${BASE}/health — is \`make dev\` running?"; \
                  echo; echo "${pass} passed, ${fail} failed"; exit 1; }

echo "2. credentials"
[ "$(jqr "$health" .runware)" = "true" ] && ok "runware key present" \
  || bad "runware:false — vision and research fall back to rules"
[ "$(jqr "$health" .linq)" = "true" ] && ok "linq key present" \
  || bad "linq:false — the number cannot reply"
echo "  ·  research_mode: $(jqr "$health" .research_mode)"

echo "3. storage"
store="$(jqr "$health" .store)"
case "$store" in
  FileStore|RedisStore) ok "durable (${store})" ;;
  *) bad "${store} — a restart loses every deal. Set CLOSER_STORE_PATH=./data" ;;
esac

echo "4. inbound listener"
inb="$(curl -fsS --max-time 5 "${BASE}/health/inbound" 2>/dev/null)" || inb=""
if [ -z "$inb" ]; then
  bad "/health/inbound did not answer"
elif [ "$(jqr "$inb" .stale)" = "true" ]; then
  bad "STALE — nothing inbound for $(jqr "$inb" .seconds_since_last_event)s. Restart scripts/listen.sh"
else
  ok "fresh (last event $(jqr "$inb" .seconds_since_last_event)s ago, $(jqr "$inb" .events) events)"
fi

echo "5. linq profile"
if "$ROOT/scripts/check_profile.sh" >/dev/null 2>&1; then ok "profile is the closer line"
else bad "wrong profile — run scripts/check_profile.sh for detail"; fi

echo "6. round trip"
if [ -z "$TO" ]; then
  warn "PREFLIGHT_TO unset — skipping. Set it to a phone that has already texted us:"
  echo "        PREFLIGHT_TO=+1XXXXXXXXXX make preflight"
else
  before="$(jqr "$inb" .messages)"
  if linq messages send-to "$TO" --message "Closer preflight — reply anything." \
       --profile "$PROFILE" >/dev/null 2>&1 \
     || linq chats create --to "$TO" --message "Closer preflight — reply anything." \
       --profile "$PROFILE" >/dev/null 2>&1; then
    ok "outbound sent to ${TO}"
    echo "     reply from that phone now — waiting 45s for it to arrive..."
    for _ in $(seq 1 45); do
      sleep 1
      now="$(jqr "$(curl -fsS "${BASE}/health/inbound" 2>/dev/null)" .messages)"
      [ -n "$now" ] && [ "$now" != "$before" ] && { ok "round trip complete"; break; }
    done
    [ "${now:-$before}" = "$before" ] && bad "no inbound within 45s — listener or webhook is down"
  else
    bad "could not send to ${TO} (Shared Line is inbound-first: they must text us first)"
  fi
fi

echo
echo "${pass} passed, ${fail} failed, ${skip} skipped"
[ "$fail" -eq 0 ]
