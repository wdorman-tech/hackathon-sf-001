# Closer — one-command ops. `make` on its own lists everything.
#
# The product is a phone number, not a URL. Two processes have to be alive for
# it to answer: the backend, and `linq webhooks listen`. `make dev` supervises
# both; `make preflight` proves the whole path before a judge tests it for you.

.DEFAULT_GOAL := help
SHELL := /bin/bash
PORT ?= 8000
PY := closer/.venv/bin/python

.PHONY: help dev backend listen health inbound preflight check-profile demo seed test logs kill setup

help:  ## show this
	@grep -hE '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev:  ## backend + supervised listener, both restart on crash
	@scripts/dev.sh

backend:  ## backend only, foreground
	@cd closer && .venv/bin/uvicorn app.main:app --port $(PORT)

listen:  ## supervised `linq webhooks listen` only
	@scripts/listen.sh

health:  ## is the backend up, and are the keys loaded
	@curl -s localhost:$(PORT)/health | $(PY) -m json.tool

inbound:  ## is the number still answering (stale => restart the listener)
	@curl -s localhost:$(PORT)/health/inbound | $(PY) -m json.tool

preflight:  ## six checks: backend, keys, store, listener, profile, round trip
	@scripts/preflight.sh

check-profile:  ## assert `linq whoami` is +12052611117, not the seller line
	@scripts/check_profile.sh

demo:  ## run the Marcus arc through /simulate, no phone needed
	@scripts/demo_arc.sh

seed:  ## add a second deal so `deals` / `1` / `2` have something to switch between
	@scripts/seed.sh

test:  ## the full suite
	@cd closer && .venv/bin/python -m pytest tests/ -q

logs:  ## tail both logs
	@tail -f logs/backend.log logs/listen.log

kill:  ## free the port (a stale backend reports linq:false and looks healthy)
	@lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t 2>/dev/null | xargs -r kill && echo "killed" || echo "nothing on :$(PORT)"

setup:  ## create the venv and install deps
	@cd closer && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && echo "ready"
