#!/usr/bin/env bash
# C5 — profile discipline.
#
# `~/.linq/config.json` holds ONE active profile shared by every process on this
# machine. `linq profile use seller` in any other terminal silently repoints
# anything that relies on the default: no error, wrong number, and you find out
# when the demo texts from the seller's line. Every `linq` call in every script
# passes --profile explicitly; this asserts that profile is the one we mean.
set -uo pipefail

PROFILE="${LINQ_PROFILE:-closer}"
EXPECTED="${LINQ_FROM_NUMBER:-+12052611117}"

command -v linq >/dev/null 2>&1 || {
  echo "FAIL: \`linq\` is not on PATH (npm install -g @linqapp/cli@latest, Node 22+)"
  exit 127
}

out="$(linq whoami --profile "$PROFILE" 2>&1)" || {
  echo "FAIL: linq whoami --profile ${PROFILE} errored:"
  echo "$out" | sed 's/^/    /'
  exit 1
}

# Compare on digits only — whoami may print "+1 205 261 1117" or "(205) 261-1117".
want="$(printf '%s' "$EXPECTED" | tr -cd '0-9')"
got="$(printf '%s' "$out"       | tr -cd '0-9')"

if [[ "$got" == *"$want"* ]]; then
  echo "ok: profile '${PROFILE}' is ${EXPECTED}"
  exit 0
fi

echo "FAIL: profile '${PROFILE}' is not ${EXPECTED}"
echo "$out" | sed 's/^/    /'
echo "    fix: linq login --profile ${PROFILE}   (or linq profile list)"
exit 1
