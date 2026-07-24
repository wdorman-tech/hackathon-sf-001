# Closer

**An AI negotiation coach that lives in iMessage.** You text Closer a used-car
listing; it researches the car's real value, then coaches every counter-offer in
real time — telling you the exact number to send and when the seller is bluffing.

The brain is a **Bayesian belief engine** (pure numpy): on every seller message it
updates a probability distribution over the seller's hidden floor price and returns
the expected-value-optimal counter. **No LLM ever estimates the floor** — the model
only translates language ↔ structure on both ends of the math. That's the point: the
game theory is real, deterministic, and inspectable.

**There is no dashboard, and no website.** Closer is a phone number. Starting a
deal, switching between deals, seeing the belief curve, and reading your lifetime
savings all happen as messages in the thread. Your phone number is the account —
Linq's webhook hands us the sender handle, so there is no signup, no login, and
no session to expire.

```
        iMessage (Linq)              +12052611117
   you ───────────────► Closer backend (local, FastAPI)
        ▲                    │  ├─ intent.py    what did this message mean?
        │  coach reply       │  ├─ engine.py    pure-numpy Bayesian floor belief
        │  + cards           │  ├─ research.py  agentic valuation (web search + cite)
        │                    │  ├─ llm.py       Runware (Claude): classify / draft / vision
        └────────────────────┘  ├─ cards.py     deal / list / stats cards, back into the thread
                                └─ store.py     per-phone deals + which one is in focus
```

- **Backend**: Python 3.12+, FastAPI, numpy. Runs **locally** (long-running uvicorn).
  Nothing is deployed; nothing needs a public URL.
- **LLM**: [Runware](https://runware.ai) native task API (`anthropic:claude@sonnet-4.6`)
  — one model for text classify/draft **and** screenshot vision.
- **Messaging**: [Linq](https://linqapp.com) Partner API v3 (real iMessage) — send,
  typing indicators, tapbacks in both directions, message effects, attachments.
- **Valuation**: Closer's own bounded research agent (web search + page reads, cited).
- **Auth**: the phone number on the inbound webhook. `user_id = "phone:+1205…"`.

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

Check it with <http://localhost:8000/health>. `static/dashboard.html` still serves
at `/` as a developer's-eye view of one deal's belief curve — it is a debugging
aid, not the product, and no user ever opens it.

### Keys (all optional for the demo)

| Var | What it unlocks | Without it |
|---|---|---|
| `RUNWARE_API_KEY` | real Claude classify/draft/vision + live research | rules classifier + mock/heuristic research |
| `LINQ_API_KEY` | real iMessage send/receive | `/simulate` keyboard flow still works |
| `CLOSER_STORE_PATH` | deals survive a restart (`FileStore`) | in-process `MemoryStore` |

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
#    → returns {"deal_id": "...", ...}

DEAL=<paste deal_id>

# 2. the seller arc — each response carries the reshaped belief in `snapshot`
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
| "fine, deal" | **CLOSED** + confetti | ~**$2,800 under ask** |

That second row is the pitch. The deal card renders it as a flat segment in the
floor line with the seller's own words underneath — the bluff, called by math.

For a warm-start after any crash: `DEMO_MODE=true` pre-seeds a deal mid-negotiation,
or `POST /demo/seed` mints one on demand.

---

## Running the real iMessage stack

Two processes on one laptop. **No tunnel, no public URL, no inbound port** — the
Linq CLI holds an outbound connection and forwards inbound events to localhost.

```bash
# 1. backend
cd closer && uvicorn app.main:app --port 8000

# 2. inbound iMessage
export LINQ_API_KEY="$(linq tokens show --profile closer | tr -d '[:space:]')"
linq webhooks listen --profile closer \
     --forward-to http://localhost:8000/webhooks/linq
```

On a Shared Line the contact must text `+12052611117` first — inbound-first. That
is not a limitation here, it *is* the signup flow: the first inbound text creates
the account. `linq contacts add <number> --profile closer` prints a share link
that opens Messages with a pre-filled draft (and renders a QR code on desktop),
so onboarding someone is one camera scan and one tap.

**If `linq webhooks listen` dies, the product is silently dead** — no error, texts
just vanish. Supervise it, and watch `/health/inbound`.

---

## What a user can say

Every capability is a message. The router's hard rule: **a message containing a
price is always a seller relay, never a command.**

| Say | Get |
|---|---|
| a listing link | new deal, research, valuation card; focus moves to it |
| anything the seller said (typed, pasted, or a screenshot) | one negotiation turn — the exact number to send back |
| `deals` | numbered list of every deal, `▶` on the focused one |
| `2` / `switch to the Civic` | focus moves; that deal's card comes back |
| `card` / `where are we` | deal card: floor estimate turn by turn, confidence, next offer |
| `stats` | lifetime savings across every closed deal |
| `undo` / `ignore that` | drop the last seller turn, replay the belief, re-recommend |
| `we have a deal` | CLOSED, confetti, dollars under ask |
| `I walked` | WALKED, logged |
| `help` | the list above |

---

## HTTP API (local only — testing, not product)

These are how you drive a rehearsal without a phone. Bind to `127.0.0.1`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhooks/linq` | Linq inbound (`message.received`) — the real entry point |
| `POST` | `/simulate` | keyboard demo `{text, deal_id?, phone?}` — no auth, no phone |
| `GET` | `/health` | store backend, Runware/Linq availability, research mode |
| `GET` | `/health/inbound` | seconds since the last inbound webhook — is the listener alive? |
| `GET` | `/state?deal_id=…` | belief curve + feed (feeds `static/dashboard.html`) |
| `POST` | `/api/deals` … | per-user CRUD, kept for scripted testing |

The negotiation snapshot the cards render (under `deal.snapshot`):
`action` (COUNTER/HOLD/WALK/ACCEPT), `offer`, `p_accept`, `zopa`, `floor_point_est`,
`floor_std`, `floor_map {floors, p}`, plus `R` (walk-away) and `V` (fair value).
`deal.trajectory()` derives the per-turn floor history the deal card plots — it
reads straight off the feed, so nothing extra is persisted.

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

See `.env.example` for the full list with comments (Runware, Linq, Research,
Storage). Storage defaults to in-process `MemoryStore` — set `CLOSER_STORE_PATH=./data`
so deals survive a restart, since the thread is the only place a user's history lives
and they cannot re-derive it.

The Clerk and Upstash variables are still read by `app/auth.py` and `app/store.py`
and still pass their tests, but nothing in the product configures them: there is no
browser to sign into, and the backend is a single long-running local process.
