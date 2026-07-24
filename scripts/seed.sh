#!/usr/bin/env bash
# D2 — a second deal that exists only to be switched to.
#
#   make seed
#
# Multi-deal is a headline feature and it needs two deals on screen with real
# variety in state. This seeds a 2016 Civic alongside whatever else is running,
# so `deals` returns a list worth looking at and `1` / `2` actually switch.
#
# Runs through /simulate, so it needs no phone — but the deals land under the
# demo user, not your phone's user_id. To seed against YOUR thread instead,
# text the listing link to +12052611117 from the demo phone.
set -uo pipefail

PORT="${PORT:-8000}"
BASE="http://localhost:${PORT}"
PY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/closer/.venv/bin/python"

curl -fsS --max-time 5 "${BASE}/health" >/dev/null 2>&1 || {
  echo "backend is not up on ${BASE} — run \`make dev\` first"; exit 1; }

send() {  # send <deal_id|""> <text> -> prints the new deal id
  "$PY" - "$BASE" "$1" "$2" <<'PY'
import json, sys, urllib.request
base, deal_id, text = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({"text": text, "deal_id": deal_id or None}).encode()
req = urllib.request.Request(f"{base}/simulate", data=body,
                             headers={"content-type": "application/json"})
with urllib.request.urlopen(req, timeout=180) as r:
    d = json.load(r)
print(d.get("deal_id") or "")
PY
}

echo "seeding a 2016 Civic to switch to..."
civic="$(send "" "https://www.cars.com/vehicledetail/2016-honda-civic-ex/")"
send "$civic" "He said: it's 13,900 and I've already got someone interested." >/dev/null
echo "  civic deal: ${civic}"

echo
echo "seeded. From the demo phone, try:"
echo "    deals        -> the numbered list"
echo "    2            -> switch to the second"
echo "    card         -> that deal's curve"
