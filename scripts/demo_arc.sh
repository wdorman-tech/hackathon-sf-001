#!/usr/bin/env bash
# D1 — the Marcus arc, driven through /simulate so it runs with no phone.
#
#   make demo                       # full arc, mock research (instant)
#   RESEARCH_MODE=live make demo    # same arc, real research (~30s on step 1)
#
# Marcus (~/seller-agent, +12054909563): 2008 Camry LE listed $6,400, true value
# ~$4,200, hidden walk-away $4,750. He anchors, concedes in shrinking steps, and
# claims other buyers when there are none.
#
# The beat that matters is message 3. It is a PURE bluff — pressure, no number,
# no movement — and the floor estimate barely moves. Everything else in this
# product is setup for that one line.
set -uo pipefail

PORT="${PORT:-8000}"
BASE="http://localhost:${PORT}"
PY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/closer/.venv/bin/python"
PAUSE="${PAUSE:-1}"

curl -fsS --max-time 5 "${BASE}/health" >/dev/null 2>&1 || {
  echo "backend is not up on ${BASE} — run \`make dev\` first"; exit 1; }

DEAL_ID=""

say() {  # say <who> <text>
  if [ "$1" = "you" ]; then printf '\n\033[1;36m  you ▸\033[0m %s\n' "$2"
  else                      printf '\033[1;33mmarcus ▸\033[0m %s\n' "$2"; fi
}

send() {  # send <text>
  local payload reply
  payload="$("$PY" -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "deal_id": sys.argv[2] or None}))' "$1" "$DEAL_ID")"
  reply="$(curl -fsS --max-time 180 -H 'content-type: application/json' \
             -d "$payload" "${BASE}/simulate")" || { echo "  (request failed)"; return 1; }
  DEAL_ID="$("$PY" -c 'import json,sys; print(json.load(sys.stdin).get("deal_id") or "")' <<<"$reply")"
  "$PY" - "$reply" <<'PY'
import json, sys, textwrap
d = json.loads(sys.argv[1])
msg = (d.get("message") or "").strip()
print("\033[1;32mcloser ▸\033[0m " + textwrap.indent(msg, "         ").lstrip())
snap = d.get("snapshot") or {}
if snap.get("floor_point_est") is not None:
    print(f"         \033[2m[ floor ≈ ${snap['floor_point_est']:,.0f}"
          f"  ±${snap.get('floor_std', 0):,.0f}"
          f"   deal likely {snap.get('zopa', 0):.0%}"
          f"   {snap.get('action', '')} ${snap.get('offer', 0):,.0f} ]\033[0m")
PY
  sleep "$PAUSE"
}

echo "═══ Marcus arc — 2008 Camry LE, listed \$6,400 ═══"

say you "https://www.cars.com/vehicledetail/2008-toyota-camry-le/"
send "https://www.cars.com/vehicledetail/2008-toyota-camry-le/"

say marcus "It's 6,400 and honestly it's worth more than that. I've had a lot of interest."
send "He said: it's 6,400 and honestly it's worth more than that. I've had a lot of interest."

say marcus "Tell you what — 6,000 for a quick sale."
send "He said: tell you what, 6,000 for a quick sale."

say marcus "I've got two other people coming to see it Saturday."
echo "         \033[2m^^^ the beat: pressure, no number, no movement\033[0m"
send "He said: I've got two other people coming to see it Saturday."

say marcus "5,600 and that's me being generous."
send "He said: 5,600 and that's me being generous."

say marcus "Fine. 5,000, final offer, I'm not going lower."
send "He said: fine. 5,000, final offer, I'm not going lower."

say you "deal"
send "deal"

echo
echo "═══ arc complete — deal ${DEAL_ID} ═══"
echo "  full state:  curl -s '${BASE}/state?deal_id=${DEAL_ID}' | jq"
