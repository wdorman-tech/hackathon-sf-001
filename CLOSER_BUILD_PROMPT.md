# CLOSER — Build Prompt for Claude Code

You are building **Closer**, a hackathon MVP: an AI negotiation coach that lives in iMessage.
Total budget: **under 4 hours**. Follow the phases in order. Commit at the end of every phase.
Bias every decision toward: works end-to-end for a live demo > clean > complete.

---

## 0. WHAT THE APP IS

Flow (this is the entire product):

1. **User texts Closer a listing link** (e.g. a used car on a marketplace) over iMessage (via Linq).
2. **Closer gets a verified expert opinion via Terac.** The expert opens the link and returns: fair
   market value, hidden costs, red flags, and key listing facts (year/miles/asking). This sets the
   user's **walk-away price R**. Closer NEVER values the item itself — the expert is the only
   source of valuation truth.
3. **Negotiation.** The user relays each seller reply into the Closer thread as **either a text
   message or a screenshot** of the seller conversation. On every seller reply, Closer:
   - classifies the message into structured signals (LLM),
   - **Bayesian-updates a probability distribution over the seller's hidden floor price**
     (pure numpy — NO LLM in the math),
   - computes the zone of possible agreement (ZOPA) and the optimal counter-offer,
   - texts the user the exact move ("counter $13,400, hold here — their floor is ~$13.5k"),
   - streams the belief distribution to a live dashboard chart.

The user is always the one talking to the seller (copilot model). Closer is the brain; two
separate threads exist conceptually: user↔seller (outside our system) and user↔Closer (Linq).

**Judging context:** this competes for a Game Theory prize. The Bayesian engine must be real,
deterministic, inspectable math. If an LLM "estimates the floor," we lose. The LLM only does
language↔structure translation on both ends of a numpy core.

---

## 1. STACK & GLOBAL RULES

- **Backend:** Python 3.12, FastAPI, uvicorn, numpy, httpx, pydantic. Single process.
- **LLM:** Runware — one endpoint for every model. `POST https://api.runware.ai/v1` with
  `Authorization: Bearer $RUNWARE_API_KEY`, body = an array of task objects. We use the
  **native** task API (not the OpenAI-compatible `/v1/chat/completions` shim) because only the
  native path takes image inputs and enforces JSON schemas — both of which we need. One model
  everywhere: `anthropic:claude@sonnet-4.6` (text + vision, 1M ctx) for listing/expert-spec/
  vision extraction and per-turn classify+draft (simplicity > latency for MVP). Model ids are
  AIR strings, `creator:family@version`; browse them at https://runware.ai/models.
  Hackathon credits: https://runware.ai/wallet, code `YCSSHACKATHON`.
- **Messaging:** Linq Partner API v3. **Assume Linq is already connected**: we have
  `LINQ_API_KEY`, `LINQ_FROM_NUMBER`, and the inbound webhook is already pointed at
  `POST {our_base_url}/webhooks/linq`. Do not build number provisioning or onboarding.
- **Experts:** Terac. **We have a Terac account ready** and `TERAC_API_KEY`. Their turnaround is
  hours, so ALL code paths must also work with `TERAC_MODE=mock` (see Phase 4). Endpoint paths
  may need adjusting to their real docs at the event — isolate every Terac HTTP call in one file.
- **Dashboard:** ONE static HTML file served by FastAPI, Chart.js from CDN, polls `GET /state`
  every 1s. No Next.js, no build step, no websockets.
- **State:** in-memory dict keyed by `chat_id`. No database. Process restart = fresh state; fine.
- **Config:** `.env` + `python-dotenv`. Create `.env.example` with every var listed in §6.
- **Vertical:** used cars only. Do not generalize.

### DO NOT BUILD (hard scope guard)
No auth, no DB, no Docker, no tests beyond the engine's, no retry queues, no scraping of the
listing URL (the expert reads the link; in mock mode facts come from the mock), no seller-side
automation, no Dynamic/payments, no multi-user handling beyond keying state by chat_id, no
webhook signature verification unless `VERIFY_LINQ_SIGNATURES=true` (default false for the demo).

### Repo layout (create exactly this)
```
closer/
  .env.example
  requirements.txt
  README.md            # run instructions + demo runbook (Phase 6)
  app/
    main.py            # FastAPI app, routes, wiring
    state.py           # Negotiation dataclass + in-memory store + state machine
    engine.py          # ALL math. Pure numpy. Zero network calls.
    runware.py         # ONLY file that talks to Runware: auth, textInference POST, JSON schema
    llm.py             # classify / extract_screenshot / draft / listing_parse
    linq.py            # send_message(chat_id/handle, text), webhook payload parsing
    terac.py           # create_job(link, photos) / get_result(job_id), mock mode
    demo.py            # seed script helpers for DEMO_MODE
  static/
    dashboard.html     # Chart.js live view
  tests/
    test_engine.py     # scripted-scenario tests for the engine
```

---

## 2. PHASE 1 — THE ENGINE (0:15–1:00) — build this FIRST

`app/engine.py`. Pure functions + one `BeliefState` class. numpy only. This file must never
import httpx/fastapi or the Runware client.

### 2.1 Grid & prior
- Inputs at negotiation start: `asking` (listing price), `R` (walk-away from expert),
  `V` (expert fair value).
- Price grid: `floors = np.linspace(0.60*asking, 1.05*asking, 61)` (61 buckets).
- Prior over the seller's floor: truncated normal, mean `0.88*asking`, std `0.10*asking`,
  evaluated on the grid and normalized to sum to 1. Store as `self.p` (np array, len 61).

### 2.2 Per-turn signals (produced by the LLM in Phase 2, consumed here)
```python
@dataclass
class Signals:
    seller_price: float | None   # price stated in THIS message, None if none stated
    concession_abs: float        # prev_seller_price - seller_price, 0 if n/a
    firmness: float              # 0..1, how firm/final the language is
    bluff_claim: bool            # "another buyer", "lots of interest", etc. w/o real movement
    final_claim: bool            # "final offer", "lowest I'll go"
    walk_threat: bool            # seller threatens to end talks
```

### 2.3 Update rule — `BeliefState.update(sig: Signals)`
Multiply `self.p` by a likelihood vector `L(f)` over the grid, then renormalize. Compose L as:

1. **Stated-price ceiling (near-hard constraint):** if `seller_price` is not None, the floor
   cannot exceed what they just offered: `L[floors > seller_price] *= 0.02`.
2. **Gap model (the core):** the seller's stated price sits some gap above their true floor.
   Expected gap shrinks when they're firm and concede little; grows when they concede big/fast:
   ```
   g = clip(0.9*concession_abs + (1 - firmness)*0.06*asking, 0.01*asking, 0.18*asking)
   sigma_g = 0.05*asking * (1.5 - firmness)        # firmer language → sharper inference
   if final_claim and concession_abs > 0.01*asking: sigma_g *= 0.6   # real "final" → spike
   L *= exp( -((seller_price - g) - floors)**2 / (2*sigma_g**2) )    # only when price stated
   ```
   Intuition check (must hold in tests): big fast concession ⇒ posterior mass shifts DOWN and
   narrows; firm tiny concession ⇒ mass shifts UP.
3. **Cheap talk:** if `bluff_claim` and `concession_abs < 0.005*asking` and no new lower price:
   apply only a whisper of tilt toward higher floors: `L *= (1 + 0.04*(floors - floors.mean())
   / floors.std())`, clipped positive. Net effect: **the posterior visibly barely moves.** This
   is the "bluff called by math" demo beat — do not strengthen it.
4. Renormalize `self.p`. Also append `(signals, posterior_copy)` to `self.history` so the
   dashboard can replay.

### 2.4 Decision layer
- `p_accept(offer) = self.p[floors <= offer].sum()`  (CDF of the floor belief).
- `zopa() = self.p[floors <= R].sum()`  → probability a deal exists at all; also return the
  band `[floor_p10, R]` where `floor_p10` is the 10th percentile of the belief.
- **Optimizer:** over candidate offers `o` on the grid with `o <= R` and
  `o >= last_user_offer` (never bid against yourself downward is impossible; enforce
  monotone increases and cap each concession at 40% of the remaining gap to the seller's
  last price):
  `EV(o) = (V - o) * p_accept(o)`; recommend `argmax EV`.
- **Walk rule:** if `zopa() < 0.25`, recommendation = WALK (restate R and why).
- **Hold rule:** if the last seller message was a bluff_claim with no movement,
  recommendation = HOLD at the current user offer.
- `recommend()` returns:
  `{action: COUNTER|HOLD|WALK|ACCEPT, offer, p_accept, ev, zopa, floor_map (belief for chart),
    floor_point_est (posterior median)}`.
  ACCEPT when `seller_price <= optimizer's best offer` or `seller_price <= R` and EV of
  accepting beats best counter.

### 2.5 Tests — `tests/test_engine.py` (pytest, keep to ~5 tests)
Script one seller arc and assert directional behavior, not exact numbers:
asking 16000, R 13000, V 14200.
1. Prior sums to 1, median in [13500, 14800].
2. Seller: 15200, small concession, firmness 0.7 → posterior median RISES vs prior.
3. Then bluff ("another buyer", no movement) → median moves < 1% → and recommend() = HOLD.
4. Then 14000 with final_claim, concession 1200 → median DROPS below 14000 and std shrinks ≥30%.
5. recommend() offer is always ≤ R and ≥ previous user offer; with the arc above the final
   recommendation lands in [13300, 13800].

**Acceptance for Phase 1:** `pytest` green. `python -m app.engine` runs a `__main__` block that
prints the scripted arc turn-by-turn (median, zopa, recommendation) so we can eyeball tuning.
Tune the constants in §2.3 until the printed arc looks believable. Commit.

---

## 3. PHASE 2 — LLM LAYER (1:00–1:40)

### 3.0 `app/runware.py` — the only file that touches Runware

One function, one httpx client, no SDK:

```python
async def text_inference(
    messages: list[dict],             # [{"role": "user"|"assistant", "content": str}]
    *,
    schema: dict | None = None,       # JSON Schema → strict structured output
    images: list[str] | None = None,  # data URIs, https URLs, or Runware media UUIDs
    system: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> str | dict: ...
```

It POSTs to `RUNWARE_BASE_URL` (default `https://api.runware.ai/v1`) with
`Authorization: Bearer $RUNWARE_API_KEY` and a one-element task array:

```json
[{
  "taskType": "textInference",
  "taskUUID": "<uuid4>",
  "model": "anthropic:claude@sonnet-4.6",
  "messages": [{"role": "user", "content": "..."}],
  "inputs": {"images": ["data:image/png;base64,iVBORw0KGgo..."]},
  "settings": {
    "systemPrompt": "...",
    "maxTokens": 2048,
    "temperature": 0,
    "outputFormat": "JSON",
    "jsonSchema": {"type": "object", "properties": {}, "required": []}
  }
}]
```

Rules:
- Fresh `uuid4` per call; the response echoes it. Read the answer from `resp["data"][0]["text"]`.
- **Never prompt-beg for JSON.** Set `settings.outputFormat: "JSON"` and pass
  `settings.jsonSchema`; Runware enforces it (a bare schema is auto-wrapped as
  `{name: "response", schema, strict: true}`). Keep a fence-stripping `json.loads` fallback
  anyway — on parse failure retry once, then raise.
- Omit `inputs` entirely when there are no images. Omit `settings.jsonSchema`/`outputFormat`
  for free-text calls (the coach message).
- Failures come back as `{"errors": [{"code", "message"}]}` — check `errors` before `data`.
- **Offline fallback:** if `RUNWARE_API_KEY` is blank, `llm.py` uses a deterministic
  rules-based classifier (regex for prices, firmness keywords, bluff phrases) so the whole
  demo runs with no network and no key. The screenshot path degrades to "paste the text
  instead". This is the stage insurance policy — build it, don't skip it.

### 3.1 `app/llm.py` — four functions

All four call `runware.text_inference`; the first three pass a JSON Schema and get structured
output back, the fourth returns free text.

1. `parse_listing(text_or_url_context) -> {title, asking, year, miles, notes}` — used only in
   mock/demo mode or when the user pastes listing text; the live-Terac path gets facts from the
   expert instead.
2. `classify_seller_message(text, prev_seller_price, asking) -> Signals` — the ONLY job is
   translation to the Signals schema (pass that schema as `jsonSchema`). Prompt must include
   3 few-shot examples: a firm small concession, a cheap-talk bluff, a big "final" concession.
   `temperature=0`.
3. `extract_from_screenshot(image_bytes) -> {seller_messages: [str], latest_seller_price: float|None}`
   — Runware vision on the same `anthropic:claude@sonnet-4.6`. Base64-encode the bytes into a
   data URI (`data:image/png;base64,...`) and pass it in `images=[...]` → `inputs.images`.
   The user screenshots their seller chat; return the seller-side messages in order (ignore
   the user's own bubbles; instruct the model that seller bubbles are typically left-aligned/
   gray, the user's right-aligned/blue). Downstream, classify only the latest seller message
   (concatenate if several arrived since last relay).
4. `draft_coach_message(recommendation, signals, expert, state) -> str` — turns the engine's
   numbers into a short, confident iMessage (≤3 short paragraphs, concrete numbers, one
   suggested reply the user can copy-paste verbatim in quotes). Never invent numbers not present
   in the recommendation/expert payload. Tone: sharp friend, no corporate voice, at most one emoji.

**Acceptance:** a `scripts`-style `__main__` in llm.py that runs classify on the three canonical
messages and prints Signals; screenshot extraction tested with any sample chat screenshot
(generate one simple test image if none at hand). Run it once **with** `RUNWARE_API_KEY` set and
once with it blank — both must produce usable Signals. Commit.

---

## 4. PHASE 3 — ORCHESTRATOR + LINQ (1:40–2:20)

`app/state.py`: per-chat `Negotiation` with a state machine:
`AWAITING_LINK → AWAITING_EXPERT → NEGOTIATING → DONE(closed|walked)`.
Fields: chat_id, listing link, expert payload, asking, R, V, BeliefState, last_seller_price,
last_user_offer, message log (for dashboard feed).

`app/linq.py`:
- `send(chat_or_handle, text)` → `POST {LINQ_BASE_URL}/v3/messages` with the from-number
  auto-selected or `LINQ_FROM_NUMBER`; Bearer `LINQ_API_KEY`.
- `parse_webhook(body) -> InboundMessage{chat_id, sender, text|None, media_urls: [..]}` —
  handle `message.received` events; ignore everything else (reactions, typing, delivery).

`app/main.py` routes:
- `POST /webhooks/linq` → parse; route by state:
  - AWAITING_LINK: if the text contains a URL → store link, reply "On it — sending this to a
    verified expert 🔧", kick Terac job (Phase 4), state → AWAITING_EXPERT. If no URL → nudge.
  - AWAITING_EXPERT: reply "Expert's still on it — hang tight." (In mock mode this state
    resolves instantly, see Phase 4.)
  - NEGOTIATING: if media present → download attachment bytes (httpx GET on the webhook's media
    url) → `extract_from_screenshot`; else use the text as the seller's message. Then:
    classify → `belief.update` → `recommend()` → `draft_coach_message` → `linq.send`. Update
    dashboard state. If action==ACCEPT/WALK and user later confirms ("done", "deal",
    "walked") → DONE.
  - Always return 200 fast; do the work inline (MVP; no queues).
- `GET /state` → JSON for the dashboard: current belief curve (floors + p), R and V lines,
  posterior median, zopa, last recommendation, and the message feed.
- `GET /` → serve `static/dashboard.html`.
- `POST /simulate` → same handler as the webhook but takes `{chat_id, text}` — this is the
  keyboard-driven fallback so the ENTIRE demo can run without touching a phone if iMessage
  misbehaves on stage.

**Acceptance:** with `TERAC_MODE=mock`, drive a full negotiation end-to-end using only
`curl POST /simulate` and watch `/state` change. Then repeat once over real iMessage. Commit.

---

## 5. PHASE 4 — TERAC (2:20–2:50)

`app/terac.py`, everything isolated here.
- `TERAC_MODE=live`: `create_job(link)` posts a job/study to Terac's API: audience = "used-car
  mechanics / auto appraisers, US"; the task instructs the expert to OPEN THE LINK and return
  STRICT JSON: `{fair_value, hidden_costs:[{item, cost}], red_flags:[str], facts:{year, miles,
  trim, asking}, confidence: low|med|high}`. Store job_id. `poll_result(job_id)` on a 60s
  background task (`asyncio.create_task` loop) — when the result lands, compute
  `R = fair_value - sum(hidden_costs)` (floor at 0.65*asking for sanity), `V = fair_value`,
  text the user the expert summary via Linq, init `BeliefState(asking, R, V)`, state →
  NEGOTIATING. Because live turnaround is HOURS: the runbook (Phase 6) says fire the real job
  at hour 0 for the demo listing; the code just needs to ingest whenever it lands. Exact
  endpoint paths/params are the ONE thing to adjust against Terac's real docs at the event —
  keep every URL in env vars (`TERAC_BASE_URL`, etc.) so it's a config fix, not a code fix.
- `TERAC_MODE=mock`: `create_job` returns instantly with a canned payload for the demo car
  (2019 Mazda CX-5, asking 16000, fair_value 14200, hidden_costs=[{timing belt service, 1200}],
  red_flags=["no service records", "vague condition wording"], confidence high) → R=13000.
  Resolves in ~3 seconds via the same background-task path so the user experience is identical.

**Acceptance:** mock mode produces the expert iMessage and flips state to NEGOTIATING; live mode
successfully creates a job (even if the result won't land for hours). Commit.

---

## 6. PHASE 5 — DASHBOARD (2:50–3:25)

`static/dashboard.html` — single file, dark theme, Chart.js via CDN, polls `/state` every 1s.
Layout (this is the demo money-shot, make it clean):
- **Main chart:** the belief curve over floors (area/line), a vertical dashed line at R labeled
  "YOUR WALK-AWAY", a vertical line at V labeled "EXPERT FAIR VALUE", and a marker at the
  posterior median labeled "their floor ≈ $X". Animate transitions (Chart.js default easing is
  fine) so each seller message visibly reshapes the curve.
- **Header strip:** ZOPA % ("Deal likely: 78%"), last recommendation (big text:
  "COUNTER $13,400 — HOLD FIRM"), seller's last price, user's last offer.
- **Right rail:** expert card (fair value, hidden costs, red flags) + live message feed.
- No build tools, no frameworks. Vanilla JS, fetch, one file.

Env (`.env.example`):
```
RUNWARE_API_KEY=                              # blank → offline rules-based fallback
RUNWARE_BASE_URL=https://api.runware.ai/v1
RUNWARE_MODEL=anthropic:claude@sonnet-4.6     # text + vision, one model for everything
LINQ_API_KEY=
LINQ_BASE_URL=https://api.linqapp.com
LINQ_FROM_NUMBER=
TERAC_MODE=mock            # mock | live
TERAC_API_KEY=
TERAC_BASE_URL=
VERIFY_LINQ_SIGNATURES=false
DEMO_MODE=false
PORT=8000
```

**Acceptance:** run the /simulate arc and watch the curve start wide → barely move on the bluff
→ collapse into a spike on the "final 14,000" message. If that sequence reads clearly on screen,
this phase is done. Commit.

---

## 7. PHASE 6 — DEMO MODE + RUNBOOK (3:25–4:00)

`app/demo.py` + README:
- `DEMO_MODE=true`: on startup, pre-seed one negotiation past the expert step (mock expert
  payload loaded, state NEGOTIATING) so the demo can start mid-story instantly after any crash.
- Write the **seller script** into README for the teammate playing the seller, mapped to the
  engine beats (each line annotated with what the chart should do):
  1. "12.4 is way too low, this car's in great shape. I could do 15,200." → curve shifts UP
  2. "I have someone coming to see it tomorrow, 15 is the lowest I'll go." → curve BARELY MOVES
     → Closer says HOLD, flags the bluff
  3. "You're killing me. 14,000 and it's yours, final." → curve SPIKES near 13.8k
  4. (after Closer's 13,500 split) "...fine. Deal." → ACCEPT, closed banner
- README demo runbook: start command, the hour-0 instruction to fire the real Terac job on the
  demo listing, the /simulate fallback commands pre-written, and a 90-second demo narration
  outline (link → expert reveal → live haggle on the chart → close at 13,500, "$2,500 under ask").
- Final pass: kill dead code, make sure a cold `pip install -r requirements.txt && uvicorn
  app.main:app` works from a fresh clone. Commit.

---

## 8. PRIORITY ORDER IF TIME RUNS SHORT

Engine + tests > /simulate-driven orchestrator > dashboard > Linq real send/receive > Terac
live mode > polish. The demo must survive with ONLY: engine + /simulate + dashboard + mock
Terac. Everything else is upside. Never let a broken integration stall you >20 minutes —
flip its mock flag and move on.
