# Closer

**An AI negotiation coach that lives in iMessage.** You text Closer a used-car
listing; it researches the car's real value, then coaches every counter-offer in
real time — telling you the exact number to send and when the seller is bluffing.

The brain is a **Bayesian belief engine** (pure numpy): on every seller message it
updates a probability distribution over the seller's hidden floor price and returns
the expected-value-optimal counter. **No LLM ever estimates the floor** — the model
only translates language ↔ structure on both ends of the math. That's the point: the
game theory is real, deterministic, and inspectable.

```
        iMessage (Linq)                          Dashboard (Vercel + Clerk)
   you ───────────────► Closer backend (local, FastAPI) ◄─────── your teammate's UI
        ▲                    │  ├─ engine.py     pure-numpy Bayesian floor belief
        │  coach reply       │  ├─ research.py   agentic valuation (web search + cite)
        └────────────────────┘  ├─ llm.py        Runware (Claude): classify / draft / vision
                                └─ store.py      per-user deals (Clerk user → many deals)
```

- **Backend**: Python 3.12+, FastAPI, numpy. Runs **locally** (long-running uvicorn).
- **LLM**: [Runware](https://runware.ai) native task API (`anthropic:claude@sonnet-4.6`)
  — one model for text classify/draft **and** screenshot vision.
- **Messaging**: [Linq](https://linqapp.com) Partner API v3 (real iMessage).
- **Valuation**: Closer's own bounded research agent (web search + page reads, cited).
- **Dashboard**: separate app on **Vercel**, users via **Clerk**, calls this backend's API.

Everything degrades gracefully: **with no API keys at all the whole app still runs
end-to-end** (rules-based classifier + mock research), so a dead network never kills a demo.

---

## Quick start (local)

```bash
cd closer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in keys, or leave blank to run keyless
pytest tests/                   # engine tests (should be green)
uvicorn app.main:app --reload --port 8000
```

Open the local dashboard at <http://localhost:8000/> and the API at
<http://localhost:8000/health>.

### Keys (all optional for the demo)

| Var | What it unlocks | Without it |
|---|---|---|
| `RUNWARE_API_KEY` | real Claude classify/draft/vision + live research | rules classifier + mock/heuristic research |
| `LINQ_API_KEY` | real iMessage send/receive | `/simulate` keyboard flow still works |
| `CLERK_ISSUER` | real per-user auth on the dashboard API | `DEV_AUTH=true` dev user |

`RUNWARE_MODEL` defaults to `anthropic:claude@sonnet-4.6`. Confirm exact model ids
with `python -m app.llm --models` (or `--smoke` for a live ping) once a key is set.

---

## Demo runbook

The entire demo can run from the keyboard — **no phone required** — via `POST /simulate`.
Set `RESEARCH_MODE=mock` in `.env` for an instant canned valuation of the demo car.

```bash
# 1. send the listing link → Closer researches it → NEGOTIATING
curl -s localhost:8000/simulate -H 'content-type: application/json' \
  -d '{"text":"https://example.com/2019-mazda-cx-5"}' | jq
#    → returns {"deal_id": "...", ...}. Open the chart at  /?deal=<deal_id>

DEAL=<paste deal_id>

# 2. the seller arc (watch the belief curve on the dashboard reshape each turn)
curl -s localhost:8000/simulate -d "{\"deal_id\":\"$DEAL\",\"text\":\"I could do 15,200.\"}"
curl -s localhost:8000/simulate -d "{\"deal_id\":\"$DEAL\",\"text\":\"Someone's coming to see it tomorrow, 15 is the lowest I'll go.\"}"
curl -s localhost:8000/simulate -d "{\"deal_id\":\"$DEAL\",\"text\":\"You're killing me. 14,000 and it's yours, final.\"}"
curl -s localhost:8000/simulate -d "{\"deal_id\":\"$DEAL\",\"text\":\"fine, deal\"}"
```

### Seller script → what the chart does (the money shot)

| The seller says… | Closer does | The belief curve |
|---|---|---|
| "I could do **15,200**." | COUNTER, holds low | shifts **up**, stays **wide** (one anchor tells us little) |
| "Someone's coming tomorrow, **15** is the lowest." | **HOLD** — flags the bluff | **barely moves** — the bluff called by math |
| "You're killing me. **14,000**, final." | COUNTER near the split | **collapses to a spike** near ~$13k |
| "fine, deal" | **CLOSED** banner | ~**$2,800 under ask** |

For a warm-start after any crash: `DEMO_MODE=true` pre-seeds a deal mid-negotiation,
or `POST /demo/seed` mints one on demand.

---

## Running the real iMessage + dashboard stack

1. **Backend, local:** `uvicorn app.main:app --port 8000`
2. **Inbound iMessage** (no tunnel needed): the Linq CLI streams and forwards to you —
   ```bash
   export LINQ_API_KEY="$(linq tokens show | tr -d '[:space:]')"
   linq webhooks listen --forward-to http://localhost:8000/webhooks/linq
   ```
   (On a Shared Line the contact must text `+12052611117` first — inbound-first. Every
   Closer reply goes back to someone who just texted us, so replies always deliver.)
3. **Expose the API to the Vercel dashboard** (the dashboard is public, the backend is
   local, so it needs a public URL):
   ```bash
   cloudflared tunnel --url http://localhost:8000      # or: ngrok http 8000
   ```
   Point the dashboard's API base at the tunnel URL, and set `CORS_ORIGINS` to the
   dashboard's Vercel domain in `.env`.
4. **Auth:** the dashboard signs users in with **Clerk** and sends the session JWT as
   `Authorization: Bearer <token>`; the backend verifies it (`app/auth.py`) and scopes
   every deal to that Clerk user. Set `CLERK_ISSUER` (+ optionally `CLERK_AUTHORIZED_PARTIES`).

---

## API

Dashboard endpoints require a Clerk bearer token (or, in dev, `X-Dev-User: <id>`).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/deals` | create a deal `{listing_link?, phone?, title?, asking?}` → kicks research |
| `GET` | `/api/deals` | list the signed-in user's deals |
| `GET` | `/api/deals/{id}` | deal detail (valuation, belief snapshot, feed, research trace) |
| `POST` | `/api/deals/{id}/link` | attach a listing link + start research |
| `POST` | `/api/deals/{id}/messages` | relay a seller message `{text?, image_url?}` → coach reply |
| `DELETE` | `/api/deals/{id}` | delete a deal |
| `POST` | `/webhooks/linq` | Linq inbound (`message.received`) — routed by deal state |
| `POST` | `/simulate` | keyboard demo `{text, deal_id?, phone?}` — no auth, no phone |
| `GET` | `/state?deal_id=…` | belief curve + feed for the dashboard (polled ~1s) |
| `GET` | `/health` | store backend, Runware/Linq/Clerk availability, research mode |

The negotiation snapshot the dashboard renders (under `deal.snapshot`):
`action` (COUNTER/HOLD/WALK/ACCEPT), `offer`, `p_accept`, `zopa`, `floor_point_est`,
`floor_std`, `floor_map {floors, p}`, plus `R` (walk-away) and `V` (fair value) lines.

---

## The engine (why the math is real)

`app/engine.py` — pure numpy, zero network. A `BeliefState` holds a posterior `p` over a
grid of candidate seller floor prices. Each seller message becomes a `Signals` struct
(price, concession, firmness, bluff/final/walk flags) and multiplies the posterior by a
likelihood: a stated-price ceiling, a gap model (firmness sharpens inference; big fast
concessions shift mass down and narrow it), and a cheap-talk term that makes a bluff
*visibly barely move* the curve. The decision layer maximizes `EV(o) = (V − o)·P(floor ≤ o)`
over legal offers, walks when a deal above fair value looks forced, and holds through bluffs.
`pytest tests/test_engine.py` asserts the directional behavior. Tune the constants in
`update()` in place — the class/method contract is frozen so a tuned engine drops in cleanly.

---

## Env reference

See `.env.example` for the full list with comments (Runware, Linq, Research, Clerk,
Storage). Storage defaults to in-process `MemoryStore`; set `UPSTASH_REDIS_REST_URL`
+ `UPSTASH_REDIS_REST_TOKEN` for durability across restarts.
