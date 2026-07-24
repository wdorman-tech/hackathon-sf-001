# CLOSER — Build Prompt for Claude Code

You are building **Closer**, a hackathon MVP: an AI negotiation coach that lives in iMessage.
Total budget: **under 4 hours**. Follow the phases in order. Commit at the end of every phase.
Bias every decision toward: works end-to-end for a live demo > clean > complete.

---

## 0. WHAT THE APP IS

Flow (this is the entire product):

1. **User texts Closer a listing link** (e.g. a used car on a marketplace) over iMessage (via Linq).
2. **Closer researches the car itself.** A bounded agentic loop reads the listing, searches the
   web for private-party comps, reads what it finds, and returns a **cited** valuation: fair
   market value, hidden costs, red flags, key facts (year/miles/trim/asking), a confidence, and
   the source URLs it actually used. That sets the user's **walk-away price R**. There is no
   human expert and no third-party valuation vendor — Closer does its own homework, and it must
   be able to show its receipts.
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
deterministic, inspectable math. If an LLM "estimates the floor," we lose. The LLM does two
jobs and neither of them is the math: (a) agentic research to establish V and R **before**
the negotiation starts, (b) language↔structure translation on both ends of a numpy core
**during** it.

---

## 1. STACK & GLOBAL RULES

- **Backend:** Python 3.12+, FastAPI, uvicorn, numpy, httpx, pydantic. Single ASGI app.
- **LLM:** Runware — one endpoint for every model. `POST https://api.runware.ai/v1` with
  `Authorization: Bearer $RUNWARE_API_KEY`, body = an array of task objects. We use the
  **native** task API (not the OpenAI-compatible `/v1/chat/completions` shim) because only the
  native path takes image inputs — which we need for screenshots. One model everywhere:
  `anthropic:claude@sonnet-4.6` (text + vision, 1M ctx) for research, listing/vision extraction,
  and per-turn classify+draft. Model ids are AIR strings, `creator:family@version`; browse them
  at https://runware.ai/models. Hackathon credits: https://runware.ai/wallet, code
  `YCSSHACKATHON`. **No direct provider SDKs** (`anthropic`, `openai`, `google-genai`).
- **Messaging:** Linq Partner API v3. **Assume Linq is already connected**: we have
  `LINQ_API_KEY`, `LINQ_FROM_NUMBER`, and the inbound webhook is already pointed at
  `POST {our_base_url}/webhooks/linq`. Do not build number provisioning or onboarding.
- **Research:** ours. `app/research.py` owns the agentic loop and every outbound fetch/search.
  Keyless DuckDuckGo by default; `SEARCH_PROVIDER=brave|serper` swaps in a keyed provider
  without touching code. `RESEARCH_MODE=mock` returns a canned payload instantly for the demo.
- **Hosting:** **Vercel.** The FastAPI app deploys as a Python serverless function; `vercel.json`
  rewrites everything to it. Consequences that shape the code (see §7):
  - No shared process memory → state lives in **Upstash Redis** (Vercel Marketplace).
  - No post-response background work → a research run happens **inline** in a function with
    `maxDuration` raised, not in a fire-and-forget `asyncio.create_task`.
- **Auth:** **Clerk** (Vercel Marketplace). The dashboard front-end holds the Clerk session and
  sends the session JWT as `Authorization: Bearer <token>`; `app/auth.py` verifies it against
  Clerk's JWKS and returns the Clerk user id, which owns the Deals. `DEV_AUTH=true` (or no Clerk
  config) falls back to a dev user so local dev and the `/simulate` demo are never blocked.
  The Linq webhook is **not** Clerk-authenticated — it's authenticated by its own signature
  (`VERIFY_LINQ_SIGNATURES`) and routed by phone/chat id.
- **Dashboard:** ONE static HTML file served by FastAPI, Chart.js from CDN, polls `GET /state`
  every 1s. No Next.js, no build step, no websockets.
- **Config:** `.env` + `python-dotenv` locally; Vercel project env vars in the cloud. Keep
  `.env.example` exhaustive (§6).
- **Vertical:** used cars only. Do not generalize.

### DO NOT BUILD (hard scope guard)
No DB beyond Upstash Redis KV, no Docker, no tests beyond the engine's and research's, no retry
queues, no seller-side automation, no payments, no multi-tenant admin, no webhook signature
verification unless `VERIFY_LINQ_SIGNATURES=true` (default false for the demo). Do not build a
Next.js front-end — Clerk is used for API auth against a static dashboard, nothing more.

### Repo layout
```
closer/
  .env.example
  requirements.txt
  vercel.json          # rewrites -> api/index.py, maxDuration for the research run
  README.md            # run instructions + deploy + demo runbook (Phase 6)
  api/
    index.py           # Vercel entrypoint: `from app.main import app`
  app/
    main.py            # FastAPI app, routes, wiring
    auth.py            # Clerk session-JWT verification (JWKS) -> user id
    state.py           # Deal model + state machine
    store.py           # MemoryStore (local) | RedisStore (Upstash, required on Vercel)
    engine.py          # ALL math. Pure numpy. Zero network calls.
    runware.py         # ONLY file that talks to Runware
    llm.py             # classify / extract_screenshot / draft / listing_parse
    research.py        # ONLY file that fetches/searches the open web. The Phase 4 agent.
    linq.py            # send(), parse_webhook(), signature verification
    demo.py            # seed script helpers for DEMO_MODE
  static/
    dashboard.html     # Chart.js live view
  tests/
    test_engine.py     # scripted-scenario tests for the engine
    test_research.py   # scripted-model tests for the research loop
```

---

## 2. PHASE 1 — THE ENGINE (0:15–1:00) — build this FIRST

`app/engine.py`. Pure functions + one `BeliefState` class. numpy only. This file must never
import httpx/fastapi or the Runware client.

### 2.1 Grid & prior
- Inputs at negotiation start: `asking` (listing price), `R` (walk-away from research),
  `V` (researched fair value).
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
  `o >= last_user_offer` (enforce monotone increases and cap each concession at 40% of the
  remaining gap to the seller's last price):
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
def text_inference(
    messages: list[dict],             # [{"role": "system"|"user"|"assistant", "content": str}]
    images: list[str] | None = None,  # data URIs, https URLs, or Runware media UUIDs
    *,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str: ...
```

It POSTs to `RUNWARE_BASE_URL` (default `https://api.runware.ai/v1`) with
`Authorization: Bearer $RUNWARE_API_KEY` and a one-element task array:

```json
[{
  "taskType": "textInference",
  "taskUUID": "<uuid4>",
  "model": "anthropic:claude@sonnet-4.6",
  "messages": [{"role": "user", "content": "..."}],
  "images": ["data:image/png;base64,iVBORw0KGgo..."],
  "maxTokens": 1024,
  "temperature": 0
}]
```

Rules:
- Fresh `uuid4` per call; the response echoes it. Read the answer from `resp["data"][0]["text"]`.
- Omit `images` entirely when there are none.
- Failures come back as `{"errors": [{"code", "message"}]}` — check `errors` before `data`.
- JSON output is requested in the system prompt and parsed with a fence-tolerant
  `json.loads` helper; on a parse failure, push the bad output back as an assistant turn, ask
  again once, then fall back. (Every caller has a non-LLM fallback, so a parse failure degrades
  rather than raises.)
- **Offline fallback:** if `RUNWARE_API_KEY` is blank, `llm.py` uses a deterministic
  rules-based classifier (regex for prices, firmness keywords, bluff phrases) and `research.py`
  uses a heuristic valuation, so the whole demo runs with no network and no key. The screenshot
  path degrades to "paste the text instead". This is the stage insurance policy — build it,
  don't skip it.

### 3.1 `app/llm.py` — four functions

1. `parse_listing(text_or_url_context) -> {title, asking, year, miles, notes}` — used when the
   user pastes listing text rather than a link, and as a cheap pre-read before research.
2. `classify_seller_message(text, prev_seller_price, asking) -> Signals` — the ONLY job is
   translation to the Signals schema. Prompt includes 3 few-shot examples: a firm small
   concession, a cheap-talk bluff, a big "final" concession. `temperature=0`.
3. `extract_from_screenshot(image_ref) -> {seller_messages: [str], latest_seller_price: float|None}`
   — Runware vision on the same `anthropic:claude@sonnet-4.6`. `image_ref` is a URL (Linq hosts
   the attachment), a data URI, or a Runware UUID, passed through as `images=[...]`.
   Return the seller-side messages in order (ignore the user's own bubbles; seller bubbles are
   typically left-aligned/gray, the user's right-aligned/blue). Downstream, classify only the
   latest seller message (concatenate if several arrived since last relay).
4. `draft_coach_message(recommendation, signals, research, state) -> str` — turns the engine's
   numbers into a short, confident iMessage (≤3 short paragraphs, concrete numbers, one
   suggested reply the user can copy-paste verbatim in quotes). It receives the **research**
   payload (fair_value, R, V, hidden_costs, red_flags, facts, sources, confidence) so it can
   cite a red flag as leverage. Never invent numbers not present in the recommendation/research
   payload. Tone: sharp friend, no corporate voice, at most one emoji.

**Acceptance:** `python -m app.llm` runs classify on the three canonical messages and prints
Signals; `python -m app.llm --smoke` pings Runware live. Run it once **with**
`RUNWARE_API_KEY` set and once with it blank — both must produce usable Signals. Commit.

---

## 4. PHASE 3 — ORCHESTRATOR + LINQ (1:40–2:20)

`app/state.py`: a `Deal` (pydantic) owned by a Clerk `user_id`, with a state machine:
`AWAITING_LINK → AWAITING_RESEARCH → NEGOTIATING → CLOSED | WALKED`.
Fields: id, user_id, chat_id, phone, title, listing_link, state, `research` payload, asking,
R, V, `research_steps` (live tool trace), `signals_log`, last_seller_price, last_user_offer,
`feed` (message log for the dashboard), `snapshot` (latest belief curve + recommendation).

Do **not** serialize the numpy `BeliefState`. Persist the ordered `signals_log` (the source of
truth) and reconstruct the live belief on demand by replaying it (`Deal.belief()`). That keeps
the store engine-agnostic — a retuned engine drops in with no migration — and it's what makes
serverless statelessness survivable.

`app/store.py`: one `Store` protocol, two backends chosen by env at import:
- `MemoryStore` — default, zero setup, local dev and `/simulate`.
- `RedisStore` — Upstash Redis over REST (httpx, no driver). **Required on Vercel.** Activates
  when `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` are set. Indexes deals by id, by
  user, by chat id, by active phone, and keeps a `pending:research` set.

`app/auth.py`: `require_user()` FastAPI dependency → Clerk user id (see §7.2).

`app/linq.py`:
- `send(to, text)` → `POST {LINQ_BASE_URL}/api/partner/v3/chats` with `LINQ_FROM_NUMBER`;
  Bearer `LINQ_API_KEY`.
- `parse_webhook(body) -> InboundMessage{chat_id, sender, text|None, media_urls: [..]}` —
  handle `message.received` events; ignore everything else (reactions, typing, delivery).
- `verify_signature(raw_body, header)` — HMAC, gated on `VERIFY_LINQ_SIGNATURES`.

`app/main.py` routes:
- `POST /webhooks/linq` → parse; find/create the Deal by chat id or phone; route by state:
  - **AWAITING_LINK:** if the text contains a URL → store link, reply "On it — digging into this
    one now 🔎", set state AWAITING_RESEARCH, then **run the research** (Phase 4) and, when it
    returns, text the summary and flip to NEGOTIATING. If no URL → nudge.
  - **AWAITING_RESEARCH:** reply "Still digging — one sec." (Research typically lands in 20-40s;
    in `RESEARCH_MODE=mock` it's instant.)
  - **NEGOTIATING:** if media present → `extract_from_screenshot` on the media URL; else use the
    text as the seller's message. Then: classify → `belief.update` → `recommend()` →
    `draft_coach_message` → `linq.send`. Persist the Deal. If action==ACCEPT/WALK and the user
    later confirms ("done", "deal", "walked") → CLOSED/WALKED.
  - Return 200 fast, and never 500 back at Linq — catch, log to the feed, apologize by text.
- `GET /api/deals`, `GET /api/deals/{id}` → **Clerk-guarded** (`Depends(require_user)`), scoped
  to that user's deals. This is what the dashboard polls.
- `GET /state` → the demo/dashboard read for the active deal: belief curve (floors + p), R and
  V lines, posterior median, zopa, last recommendation, research payload + sources, research
  step trace, and the message feed.
- `GET /` → serve `static/dashboard.html`.
- `POST /simulate` → same handler as the webhook but takes `{chat_id, text}` — the
  keyboard-driven fallback so the ENTIRE demo can run without touching a phone.
- `GET /healthz` → `{ok, store: "MemoryStore"|"RedisStore", runware: bool, research_mode}`.

**Acceptance:** with `RESEARCH_MODE=mock`, drive a full negotiation end-to-end using only
`curl POST /simulate` and watch `/state` change. Then repeat once over real iMessage. Commit.

---

## 5. PHASE 4 — AGENTIC PRODUCT RESEARCH (2:20–2:50)

`app/research.py`. **The only file allowed to fetch or search the open web.** No human expert,
no valuation vendor: Closer forms its own opinion and shows its sources.

### 5.1 Contract

```python
run_research(link: str, *, asking: float | None = None,
             max_steps: int | None = None,
             on_step: Callable[[dict], None] | None = None) -> dict
```

Returns — and this is what the rest of the app consumes:

```json
{
  "fair_value": 14200,
  "hidden_costs": [{"item": "timing belt service due", "cost": 1200}],
  "red_flags": ["no service records", "priced ~13% over comparable listings"],
  "facts": {"year": 2019, "make": "Mazda", "model": "CX-5",
            "trim": "Touring AWD", "miles": 68000, "asking": 16000},
  "confidence": "low|med|high",
  "sources": [{"title": "...", "url": "https://...", "note": "what it established"}],
  "reasoning": "2-3 sentences the buyer could repeat to the seller",
  "steps": [{"tool": "web_search", "arg": "...", "note": "5 results", "thought": "..."}],
  "listing_link": "https://..."
}
```

Derived by `to_valuation(payload, asking)`:
`V = fair_value`, `R = fair_value - sum(hidden_costs)`, floored at `0.65 * asking`.
`research_summary(payload)` renders the iMessage the user gets when research lands, including
the source domains — the receipts are part of the product, not a footnote.

### 5.2 The loop

**Step 0 (deterministic, always):** fetch the listing URL, strip it to text (stdlib
`html.parser`, scripts/styles dropped, capped at `RESEARCH_PAGE_CHARS`). That text seeds the
transcript so even a zero-tool run has real facts.

Then up to `RESEARCH_MAX_STEPS` (default 6) iterations. Each turn the model returns ONLY a JSON
object, one of:

```json
{"thought": "...", "tool": "web_search", "query": "2019 Mazda CX-5 Touring AWD 68k private party value"}
{"thought": "...", "tool": "fetch_page", "url": "https://www.kbb.com/mazda/cx-5/2019/"}
{"thought": "...", "tool": "finish", "fair_value": 14200, "hidden_costs": [...], ...}
```

Our code executes the tool and appends an `OBSERVATION (<tool>): {json}` user turn (capped at
4k chars). The system prompt hands the model a research plan — (1) nail the exact vehicle,
(2) find private-party comps for that year/trim/mileage, (3) check known problems/maintenance
due at this mileage, (4) price the deferred work — and one hard rule: **sources must be URLs it
actually fetched or that came back from a search; never invent one.** With ≤1 call left, we
inject "respond with the `finish` JSON now."

### 5.3 Tools

- `fetch_page(url)` → `{url, text, error}`. `http(s)` only, redirects followed, non-text
  content types rejected. Never raises.
- `web_search(query)` → `{query, results:[{title, url, snippet}], error}`. Never raises.
  Provider order = `SEARCH_PROVIDER` then keyless DuckDuckGo (`html.duckduckgo.com/html/`,
  redirect links unwrapped from `uddg=`, sponsored `y.js?ad_domain=` rows filtered out).
  `brave` and `serper` are drop-in via `BRAVE_API_KEY` / `SERPER_API_KEY`.

### 5.4 Guardrails — every failure still yields a usable number

- **Sanity clamp:** `fair_value` is clamped into `[0.55*asking, 1.05*asking]`. The agent does
  not get to hand the engine an absurd V.
- **No citations, no confidence:** a payload with an empty `sources` list can't claim `high`;
  it's downgraded to `med`.
- **Search blocked/rate-limited** → `results: []` plus a note; the agent keeps going and lowers
  its own confidence rather than aborting.
- **Bad JSON from the model** → the turn is re-prompted once, and the run continues.
- **Out of steps without finishing** → heuristic payload, `confidence: "low"`.
- **No `RUNWARE_API_KEY`** → heuristic payload straight from the listing text: `fair_value =
  0.89 * asking` (the typical private-party list-to-sale gap), year/miles by regex, red flags
  from as-is / salvage / missing-service-records wording.
- **`RESEARCH_MODE=mock`** → canned payload for the demo car (2019 Mazda CX-5, asking 16000,
  fair_value 14200, hidden_costs=[{timing belt service, 1200}] → R=13000, three real source
  URLs), returned instantly with a plausible step trace so the UX is identical.

`on_step` fires after every tool call, so `main.py` can append to `Deal.research_steps` and the
dashboard can stream "🔎 searching comps… 📄 reading kbb.com…" live. That trace is the demo
beat that proves the research is real.

### 5.5 Threading

`run_research` is **blocking** (sync httpx, like the rest of the app) and takes 20-40s. Callers:
- **Local (uvicorn):** `await asyncio.to_thread(research.run_research, link, on_step=...)` —
  never block the event loop.
- **Vercel:** run it inline inside the request with `maxDuration` raised in `vercel.json`
  (§7.1). Do **not** use `asyncio.create_task` / `BackgroundTasks` and return early — a
  serverless function is frozen after it responds and the work silently dies.

### 5.6 Tests — `tests/test_research.py`

Scripted fake model + stubbed tools, no network, no key. Assert: the loop runs tools then
finishes; the trace order; R/V derivation; the fair-value clamp; the `0.65*asking` floor on R;
uncited-high → med; bad-JSON recovery; budget exhaustion → heuristic; `on_step` streaming;
offline heuristic facts/red-flags; a dead listing page still returns a payload; mock mode shape;
the summary message contains the numbers and the source domains. Plus unit tests for
`html_to_text`, DDG redirect unwrapping, and ad filtering.

**Acceptance:** `pytest` green. `python -m app.research <listing-url>` prints the live trace and
the final payload against a real listing. `RESEARCH_MODE=mock python -m app.research` returns
instantly with the demo payload. Commit.

---

## 6. PHASE 5 — DASHBOARD (2:50–3:25)

`static/dashboard.html` — single file, dark theme, Chart.js via CDN, polls `/state` every 1s.
Layout (this is the demo money-shot, make it clean):
- **Main chart:** the belief curve over floors (area/line), a vertical dashed line at R labeled
  "YOUR WALK-AWAY", a vertical line at V labeled "FAIR VALUE", and a marker at the posterior
  median labeled "their floor ≈ $X". Animate transitions (Chart.js default easing is fine) so
  each seller message visibly reshapes the curve.
- **Header strip:** ZOPA % ("Deal likely: 78%"), last recommendation (big text:
  "COUNTER $13,400 — HOLD FIRM"), seller's last price, user's last offer.
- **Right rail:** the **research card** — fair value, hidden costs, red flags, confidence chip,
  and the clickable source list — plus the live tool trace while research is running, then the
  message feed.
- No build tools, no frameworks. Vanilla JS, fetch, one file.

Env (`.env.example` — keep this exhaustive):
```
RUNWARE_API_KEY=                              # blank → offline rules + heuristic valuation
RUNWARE_BASE_URL=https://api.runware.ai/v1
RUNWARE_MODEL=anthropic:claude@sonnet-4.6     # text + vision, one model for everything

LINQ_API_KEY=
LINQ_BASE_URL=https://api.linqapp.com
LINQ_FROM_NUMBER=

RESEARCH_MODE=live         # live | mock
RESEARCH_MAX_STEPS=6
RESEARCH_TIMEOUT_S=20
RESEARCH_PAGE_CHARS=8000
SEARCH_PROVIDER=ddg        # ddg (keyless) | brave | serper
SEARCH_RESULTS=5
BRAVE_API_KEY=
SERPER_API_KEY=

CLERK_ISSUER=              # https://<app>.clerk.accounts.dev
CLERK_JWKS_URL=            # defaults to {issuer}/.well-known/jwks.json
CLERK_AUTHORIZED_PARTIES=  # CSV of allowed `azp`
DEV_AUTH=false             # true → bypass Clerk, use DEV_USER_ID
DEV_USER_ID=demo_user

UPSTASH_REDIS_REST_URL=    # required on Vercel
UPSTASH_REDIS_REST_TOKEN=

VERIFY_LINQ_SIGNATURES=false
DEMO_MODE=false
PORT=8000
```

**Acceptance:** run the /simulate arc and watch the curve start wide → barely move on the bluff
→ collapse into a spike on the "final 14,000" message. If that sequence reads clearly on screen,
this phase is done. Commit.

---

## 7. DEPLOY — VERCEL + CLERK

### 7.1 Vercel

`api/index.py` is the entrypoint; Vercel's Python runtime serves an ASGI app exported as `app`:

```python
from app.main import app   # noqa: F401
```

`vercel.json`:

```json
{
  "functions": { "api/index.py": { "maxDuration": 60, "memory": 1024 } },
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }]
}
```

- `maxDuration: 60` exists **because of Phase 4** — a research run is inline and takes 20-40s.
- Provision the two integrations from the Marketplace, which write their env vars into the
  project for you:
  ```
  vercel integration add upstash     # Redis → UPSTASH_REDIS_REST_URL/TOKEN
  vercel integration add clerk       # auth  → Clerk keys
  ```
- Everything else: `vercel env add <NAME>` (or the dashboard) for `RUNWARE_API_KEY`,
  `LINQ_API_KEY`, `LINQ_FROM_NUMBER`, `RESEARCH_MODE`. Pull them locally with `vercel env pull`.
- Deploy: `vercel` (preview) / `vercel --prod`. Then point the Linq inbound webhook at
  `https://<deployment>/webhooks/linq`.
- **Serverless consequences, restated because they bite:** in-process memory is not shared
  between invocations, so `UPSTASH_*` must be set in the cloud or state vanishes between
  messages; and no work survives the response, so research runs inline (§5.5).

### 7.2 Clerk

- The dashboard front-end holds the Clerk session and sends `Authorization: Bearer <session JWT>`
  on every `/api/*` call.
- `app/auth.py` verifies RS256 against Clerk's JWKS (`pyjwt[crypto]`, `PyJWKClient`), checks
  `iss` against `CLERK_ISSUER`, optionally checks `azp` against `CLERK_AUTHORIZED_PARTIES`, and
  returns `sub` — the Clerk user id that owns the Deals.
- `require_user()` is a FastAPI dependency; use it on every user-facing route.
- Not configured, or `DEV_AUTH=true` → returns `DEV_USER_ID` (or the `X-Dev-User` header). Local
  dev, tests, and the `/simulate` demo path are never blocked by auth.
- The Linq webhook stays unauthenticated by Clerk — Linq is a machine, not a user. It's gated by
  `VERIFY_LINQ_SIGNATURES` and routed by chat id / phone.

---

## 8. PHASE 6 — DEMO MODE + RUNBOOK (3:25–4:00)

`app/demo.py` + README:
- `DEMO_MODE=true`: on startup, pre-seed one negotiation past the research step (mock research
  payload loaded, state NEGOTIATING) so the demo can start mid-story instantly after any crash.
- Write the **seller script** into README for the teammate playing the seller, mapped to the
  engine beats (each line annotated with what the chart should do):
  1. "12.4 is way too low, this car's in great shape. I could do 15,200." → curve shifts UP
  2. "I have someone coming to see it tomorrow, 15 is the lowest I'll go." → curve BARELY MOVES
     → Closer says HOLD, flags the bluff
  3. "You're killing me. 14,000 and it's yours, final." → curve SPIKES near 13.8k
  4. (after Closer's 13,500 split) "...fine. Deal." → ACCEPT, closed banner
- README demo runbook: start command, deploy command, the `/simulate` fallback commands
  pre-written, and a 90-second demo narration outline (link → **watch the research trace stream
  in, then the cited valuation land** → live haggle on the chart → close at 13,500, "$2,500
  under ask, and here's exactly why").
- **Stage insurance, in order:** run the real research live if the venue wifi is good; if it's
  flaky, `RESEARCH_MODE=mock` gives the identical UX instantly. Have both env files ready.
- Final pass: kill dead code, make sure a cold `pip install -r requirements.txt && uvicorn
  app.main:app` works from a fresh clone, and that `vercel --prod` is green. Commit.

---

## 9. PRIORITY ORDER IF TIME RUNS SHORT

Engine + tests > /simulate-driven orchestrator > dashboard > research live mode > Linq real
send/receive > Vercel deploy > Clerk > polish. The demo must survive with ONLY: engine +
/simulate + dashboard + `RESEARCH_MODE=mock`. Everything else is upside. Never let a broken
integration stall you >20 minutes — flip its mock flag and move on.
