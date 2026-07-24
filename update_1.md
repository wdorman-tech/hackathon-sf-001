# Update 1 — Closer to a fully working MVP

**Written**: 2026-07-24, after a live audit of `main` (`71873a6`).
**Target**: dashboard hosted on Vercel, Clerk auth working end to end, backend
running **locally for the whole event**, iMessage thread live, screenshots working.
**Shape**: 4 phases, 4 parallel lanes, one branch per lane.

---

## 0. Where we actually are (verified, not assumed)

Everything below was run against the real services today, not read off the README.

### Works

| Thing | Evidence |
|---|---|
| Bayesian engine | `pytest tests/` → **269 passed** in 0.55s |
| Negotiation loop | Full 4-turn arc through `POST /simulate` with real Claude via Runware |
| Bluff detection | "someone's coming tomorrow, 15 is lowest" → **HOLD**, floor estimate moved $13,931 → $13,940 (barely) |
| Convergence | "14,000 final" → floor $12,942, `p_accept` **85%**; "fine, deal" → CLOSED $13,200, $2,800 under ask |
| Research agent (live) | Real run on a 2008 Camry: DDG search → KBB/Edmunds/CarComplaints, fair value $3,500, 5 hidden costs, 5 red flags, `confidence: med`, sources cited |
| Linq account | `linq doctor --profile closer` → 6/6 pass, token valid, `+12052611117`, 1 webhook active |
| Single-deal dashboard | `static/dashboard.html` — belief curve, KPIs, valuation, research trace, feed, 1s poll |
| Clerk verification code | `app/auth.py` — JWKS, RS256 only, `iss` verified, `azp` allow-list, fails closed when `VERCEL_ENV=production` |
| Per-user deal API | `/api/deals` CRUD exists and is scoped by `user_id` |

### Broken or missing

| # | Gap | Detail |
|---|---|---|
| B1 | **Screenshot path 400s** | `app/runware.py:83` sends `images` at task top level → `unsupportedParameter: 'images' … not supported for text inference`. Verified working shape in §Lane A. |
| B2 | **No dashboard app** | No deal list, no open/closed views, no Clerk sign-in, no Next.js project. `ideas-dash/` is the hackathon-ideas chart page, unrelated. |
| B3 | **Identity is split** | iMessage deals are created with `user_id = "phone:+1205…"` (`main.py:270`). The dashboard lists by Clerk `sub`. **A deal you text in will never appear in the dashboard** until these are linked. |
| B4 | **Nothing deployed** | No Vercel project, no tunnel, no public URL. |
| B5 | **Inbound iMessage not wired** | No `linq webhooks listen --forward-to` process running. Texting `+12052611117` currently hits nothing. |
| B6 | **`RESEARCH_MODE=mock`** | `.env` serves the canned Mazda payload; the live agent that works is switched off. |
| B7 | **`MemoryStore`** | Every deal dies on backend restart. No Upstash, no file persistence. |
| B8 | **Live research degrades to $0** | cars.com / autotrader / kbb return HTTP 403. With no asking price parsed, the fallback emits `V=0, R=0` and a "$0 fair value" summary. |
| B9 | **Stale process on :8010** | Started 14:21, before `LINQ_API_KEY` landed in `.env`; reports `linq:false`. A fresh boot reports `linq:true`. Restart it. |

---

## 1. Target architecture (local backend, hosted dashboard)

```
     iMessage                                          Browser
  +12052611117                                   closer.vercel.app
        │                                                │
        │ Linq relay                            Clerk sign-in (hosted)
        ▼                                                │
  linq webhooks listen ──┐                     Next.js server (Vercel)
   (your laptop)         │                     app/api/closer/[...path]
                         ▼                        │  auth().getToken()
              ┌──────────────────────┐            │  Authorization: Bearer <JWT>
              │  Closer backend      │◄───────────┘  (server-side only)
              │  localhost:8000      │            over the stable tunnel URL
              │  FastAPI + numpy     │
              └──────────────────────┘
                         ▲
                  cloudflared / ngrok
                  https://closer.<stable>.dev
```

Two decisions worth stating up front, because they remove whole classes of MVP pain:

**The browser never talks to the tunnel directly.** All dashboard reads/writes go
through Next.js route handlers on Vercel, which attach the Clerk token server-side
and forward to the tunnel. Consequences: no CORS config to get wrong, the tunnel URL
is never exposed to the public, no mixed-content risk, and swapping the tunnel URL is
one Vercel env var — no client rebuild.

**The tunnel hostname must be stable.** A `cloudflared tunnel --url` quick tunnel mints
a new random hostname every restart, and every restart then means editing a Vercel env
var and redeploying. Use one of:

- `ngrok http 8000 --domain=<your-static-domain>.ngrok-free.app` (free tier includes one static domain), or
- a named Cloudflare tunnel: `cloudflared tunnel create closer` + `cloudflared tunnel route dns closer closer.<yourdomain>`.

Pick one in Phase 0 and never think about it again.

---

## 2. Frozen contracts (agree on these before anyone writes code)

Lanes only run in parallel if the seams are frozen first. These are the seams.

### 2.1 HTTP API — already implemented, do not change shapes

| Method | Path | Auth | Body / params |
|---|---|---|---|
| `POST` | `/api/deals` | Clerk | `{listing_link?, phone?, title?, asking?}` |
| `GET` | `/api/deals` | Clerk | → `{deals: Deal[]}` |
| `GET` | `/api/deals/{id}` | Clerk | → `Deal` |
| `DELETE` | `/api/deals/{id}` | Clerk | → `{ok: true}` |
| `POST` | `/api/deals/{id}/link` | Clerk | `{listing_link}` |
| `POST` | `/api/deals/{id}/messages` | Clerk | `{text?, image_url?}` → `{message, deal}` |
| `GET` | `/state?deal_id=…` | none | → `{deal}` (dashboard polling) |
| `GET` | `/health` | none | → `{ok, store, runware, linq, clerk, research_mode}` |
| `POST` | `/webhooks/linq` | HMAC | Linq `message.received` |
| `POST` | `/simulate` | none | `{text, deal_id?, phone?}` — keyboard demo |

**New in this plan** (Lane A owns, Lane B codes against from hour zero):

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/me/phone` | Clerk | `{phone}` → link this phone to the Clerk user, claim existing `phone:` deals |
| `GET` | `/api/me` | Clerk | → `{user_id, phone, deal_counts:{open,closed,walked}}` |
| `POST` | `/api/deals/{id}/screenshot` | Clerk | `{image_base64, media_type}` → same return as `/messages` |

### 2.2 `Deal` JSON (from `state.py:108`, `deal.public()`)

```jsonc
{
  "id": "d6934c6d7390",
  "title": "2019 Mazda CX-5 Touring",
  "state": "AWAITING_LINK|AWAITING_RESEARCH|NEGOTIATING|CLOSED|WALKED",
  "listing_link": "https://…",
  "phone": "+1205…",
  "asking": 16000.0, "R": 13000.0, "V": 14200.0,
  "research": { "fair_value": 14200, "hidden_costs": [{"item","cost"}],
                "red_flags": ["…"], "sources": [{"title","url","note"}],
                "confidence": "low|med|high", "facts": {"year","make","model","trim","miles"} },
  "research_steps": [{"tool","arg","note","thought"}],
  "last_seller_price": 14000.0,
  "last_user_offer": 13200.0,
  "snapshot": {
    "action": "COUNTER|HOLD|WALK|ACCEPT",
    "offer": 13200.0, "p_accept": 0.85,
    "floor_point_est": 12941.5, "floor_std": 640.2, "zopa": [12900, 14200],
    "floor_map": { "floors": [9000, 9100, …], "p": [0.0001, …] },
    "asking": 16000, "R": 13000, "V": 14200, "coach_message": "…"
  },
  "feed": [{"role":"seller|closer","text":"…","ts":1753380000.0,
            "signals": {…}, "recommendation": {…}}],
  "created_at": 1753379000.0, "updated_at": 1753380000.0
}
```

`snapshot` is `null` until the first seller message. `research` is `null` until
research finishes. **Every dashboard component must render both null states** — that
is what the judges see in the first 30 seconds of the demo.

### 2.3 Deal grouping for the dashboard

- **Open** = `state ∈ {AWAITING_LINK, AWAITING_RESEARCH, NEGOTIATING}`
- **Closed** = `state == CLOSED`
- **Walked** = `state == WALKED`

Savings on a closed deal = `asking - (last_user_offer ?? last_seller_price)`. Do not
invent a different formula; the backend uses this one in the close message
(`main.py:240`).

### 2.4 File ownership (merge-conflict firewall)

| Path | Owner lane | Anyone else |
|---|---|---|
| `closer/app/runware.py`, `llm.py`, `research.py`, `store.py`, `state.py`, `main.py` | A | read only |
| `closer/tests/**` | A (D may add fixtures under `tests/fixtures/`) | — |
| `dashboard/**` (new Next.js app) | B | read only |
| `closer/static/dashboard.html` | B may delete at the very end; nobody edits | — |
| `.env`, `.env.example`, `vercel.json`, `Makefile`, `scripts/**` | C | propose via C |
| `update_1.md`, `DEMO.md`, `LINQ.md` | D | append-only sections |

Two rules keep merges boring: **one lane per file**, and **rebase on `main` before
every PR**.

---

## 3. Phases

### Phase 0 — Setup, 30 minutes, everyone together

Nobody starts lane work until all of these are green. Doing them in parallel with the
build is how teams lose an hour to "which Clerk instance are we on".

1. **Free port 8000.** An unrelated Python static server holds it right now:
   ```bash
   lsof -nP -iTCP:8000 -sTCP:LISTEN     # confirm it is not Closer
   kill <pid>
   ```
   Also kill the stale Closer on :8010 (gap B9) — it has no Linq key.
2. **Provision Clerk.** One Clerk application, dev instance. Capture:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (dashboard)
   - `CLERK_ISSUER` = the Frontend API URL, e.g. `https://<slug>.clerk.accounts.dev` (backend)
   Enable email + Google sign-in. Nothing else.
3. **Provision Vercel.** `vercel link` a new project named `closer-dashboard`, root
   directory `dashboard/`. Do not deploy anything yet.
4. **Claim a stable tunnel hostname** (ngrok static domain or named cloudflared tunnel).
   Write it into the team channel. This is `CLOSER_API_BASE`.
5. **Cut the branches**:
   ```bash
   git checkout main && git pull
   for l in backend dashboard infra messaging; do git branch lane/$l; done
   ```
6. **Paste §2 into the team channel.** The contract is the coordination mechanism.

**Gate**: `curl -s localhost:8000/health` returns `{"ok":true,…,"linq":true}` from a
freshly booted backend, and the Clerk + Vercel + tunnel credentials are in the channel.

---

### Phase 1 — Parallel build (~2–3 hours, 4 lanes, no cross-blocking)

Each lane below is self-contained and testable alone. Details in §4.

| Lane | Branch | Deliverable | Blocks nothing |
|---|---|---|---|
| **A — Backend** | `lane/backend` | Vision fix, identity link, durable store, research hardening | Lane B codes against the contract, not against A's code |
| **B — Dashboard** | `lane/dashboard` | Next.js + Clerk + deals list/detail, deployed to a Vercel preview | Uses `USE_MOCK=1` fixtures until A merges |
| **C — Infra** | `lane/infra` | Tunnel, Vercel env, proxy route wiring, one-command boot | Owns `.env` and scripts only |
| **D — Messaging + demo** | `lane/messaging` | Live iMessage round trip, Marcus arc, demo script, fixtures | Touches no shared source files |

---

### Phase 2 — Integration (~45 minutes, sequential, one person driving)

Merge order matters. Merge in this order, running the gate after each:

1. **A → main.** Gate: `pytest` green (target: 280+ tests), `/health` shows `runware:true, linq:true, store:FileStore`, screenshot smoke passes.
2. **C → main.** Gate: `make dev` boots backend + tunnel + Linq listener in one command; tunnel URL responds to `curl https://<tunnel>/health`.
3. **B → main.** Gate: Vercel preview signs in with Clerk, lists deals, opens a deal, renders the belief curve.
4. **D → main.** Gate: full demo script runs start to finish without a human editing anything.

**End-to-end acceptance test** (the actual MVP definition — run it before calling it done):

```
1. Sign in to closer-dashboard.vercel.app with Clerk         → dashboard, 0 deals
2. Settings → enter your phone → POST /api/me/phone          → "phone linked"
3. Text a listing link from that phone to +12052611117       → Closer replies "researching…"
4. Refresh the dashboard                                     → the deal is THERE, owned by your Clerk user
5. Marcus (or a human) texts back "15,200"                   → coach reply arrives in iMessage
6. Dashboard deal detail                                     → belief curve reshapes, action = COUNTER
7. Screenshot a chat from another app, text it in            → price extracted, curve updates
8. Text "fine, deal"                                         → deal moves to Closed, savings shown
9. Sign out, sign in as a second Clerk user                  → sees NONE of user 1's deals
```

Step 4 is the one that proves B3 is fixed. Step 9 is the one that proves auth is real.

---

### Phase 3 — Demo hardening (~45 minutes, whoever is free)

1. **Warm start**: `DEMO_MODE=true` pre-seeds a mid-negotiation deal; verify `POST /demo/seed` still mints one on demand.
2. **Kill-switch fallbacks**: rehearse the demo with the network off — rules classifier + `RESEARCH_MODE=mock` must still complete the arc.
3. **Tunnel death drill**: kill the tunnel mid-demo, restart it, confirm the dashboard recovers without a redeploy (it will, if the URL is stable).
4. **Two rehearsals, timed.** Every person can drive it solo.
5. **Screenshot the money moment** (the belief curve barely moving on the bluff) as a static fallback slide.

---

## 4. Lane detail

### Lane A — Backend (`lane/backend`)

Owner: whoever knows Python best. Everything here is local-only; no deploy concerns.

**A1. Fix the screenshot path (B1) — highest value, ~30 min.**

The failing call, verified today:
```
Runware HTTP 400: unsupportedParameter — Unsupported use of 'images' parameter.
This parameter is not supported for text inference.
```
I probed three shapes against the live API. Results:

| Shape | Result |
|---|---|
| `task["images"] = [...]` (current) | ❌ `unsupportedParameter` |
| `content: [{type:"image_url", image_url:{url}}]` (OpenAI style) | ❌ `providerBadRequest` from Anthropic |
| `content: [{type:"image", source:{type:"base64", media_type, data}}]` | ✅ **works** — read "$15,200" off a test screenshot |
| `source: {type:"url", url}` | ❌ `providerBadRequest` — **URLs are not accepted** |

So: images must ride as Anthropic-style content parts on the last user message, and
**any URL (including Linq media URLs) must be downloaded and base64'd first**. Patch
`runware.py` only — `llm.py` callers keep passing `images=[...]` and stay unchanged:

```python
def _image_part(ref: str) -> dict:
    """URL | data URI | raw base64 -> an Anthropic image content part.
    Runware rejects source.type='url', so a URL is fetched and inlined."""
    if ref.startswith("data:"):
        header, _, b64 = ref.partition(",")
        media = header[5:].split(";")[0] or "image/png"
    elif ref.startswith(("http://", "https://")):
        r = httpx.get(ref, timeout=30.0, follow_redirects=True)
        r.raise_for_status()
        media = r.headers.get("content-type", "image/png").split(";")[0]
        b64 = base64.b64encode(r.content).decode()
    else:                                   # already raw base64
        media, b64 = "image/png", ref
    return {"type": "image",
            "source": {"type": "base64", "media_type": media, "data": b64}}
```
then, in `text_inference`, instead of `task["images"] = images`:
```python
if images:
    last = turns[-1] if turns else {"role": "user", "content": ""}
    text = last["content"] if isinstance(last["content"], str) else ""
    last["content"] = [{"type": "text", "text": text}] + [_image_part(i) for i in images]
    if not turns:
        turns.append(last)
```
Also cap the image: Anthropic rejects very large payloads, and a phone screenshot is
often 3–5 MB. Downscale to max 1568px on the long edge before encoding.

Tests: one unit test per input form (data URI / URL / raw b64) asserting the emitted
task JSON, using a stubbed `httpx`. Plus a live smoke behind an env flag.

**A2. Link phone ↔ Clerk user (B3) — the integration blocker, ~45 min.**

Today `_resolve_or_create` (`main.py:265`) stamps `user_id=f"phone:{sender}"`, so
texted deals are invisible to the dashboard. Add to the `Store` protocol and both
backends:

```python
def link_phone(self, phone: str, user_id: str) -> None: ...
def user_for_phone(self, phone: str) -> Optional[str]: ...
```
- `MemoryStore`: a dict. `RedisStore`: `SET phone:{phone}:user {user_id}`.
- `_resolve_or_create` looks up `user_for_phone(sender)` and uses it when present,
  falling back to the `phone:` id.
- `POST /api/me/phone` (Clerk-authed) writes the mapping **and claims existing deals**:
  re-owner every deal whose `user_id == f"phone:{phone}"` to the Clerk `sub`, so a deal
  started before linking still shows up.
- Normalize phones to E.164 on both sides (`+1205…`), one helper, used everywhere.

Hackathon-grade trust model: we accept the phone the signed-in user claims, no SMS
verification. Say so in a code comment — it is a deliberate, documented shortcut, and
`link_phone` refuses to steal a phone already mapped to a different user id.

**A3. Durable local store (B7) — ~30 min.**

The backend is local for the entire event, so Upstash is unnecessary ceremony. Add a
`FileStore`: same `Store` protocol, JSON-per-deal under `data/deals/`, atomic write via
tmp + `os.replace`, loaded into memory on boot. Selection order in `get_store()`:
Upstash if configured → `CLOSER_STORE_PATH` if set → `MemoryStore`. Default
`CLOSER_STORE_PATH=./data` in `.env.example` so restarts stop eating the demo.

**A4. Research hardening (B6, B8) — ~30 min.**

- Flip `.env` to `RESEARCH_MODE=live` (keep `mock` documented as the panic switch).
- When the listing fetch 403s **and** no asking price was found, do not emit `V=0/R=0`.
  Set `state=AWAITING_ASKING` semantics the cheap way: keep the deal in `NEGOTIATING`
  but have the coach reply ask for the number — "cars.com blocked me; what are they
  asking?" — and accept a bare number to set `asking`, then recompute `V`/`R`.
- Add a `User-Agent` header on `fetch_page` — some 403s are naked-client blocks.
- Cap research wall time at ~40s so a slow crawl never stalls a live text thread.

**A5. Ops polish — ~15 min.**

- `/health` also reports `store` path and deal count — one-glance demo readiness.
- Log every inbound/outbound Linq message to stdout with the deal id.

**Lane A gate**
```bash
pytest tests/ -q                                    # all green
curl -s localhost:8000/health | jq                  # runware:true linq:true store:FileStore
python -m app.llm --vision path/to/screenshot.png   # prints extracted price
curl -s localhost:8000/api/me -H 'X-Dev-User: u_1'  # returns counts
```

---

### Lane B — Dashboard (`lane/dashboard`)

Owner: whoever is fastest in React. **Not blocked by Lane A** — build against §2.2
fixtures with `USE_MOCK=1` and swap to the real base URL at integration.

**B1. Scaffold.** `dashboard/` at repo root, Next.js App Router + TypeScript +
Tailwind + shadcn. Vercel project root directory = `dashboard`.

**B2. Clerk.** `@clerk/nextjs`. `<ClerkProvider>` in the root layout, `middleware.ts`
protecting `/deals(.*)` and `/settings`, `<SignIn>`/`<SignUp>` on catch-all routes,
`<UserButton>` in the header. Marketing landing at `/` stays public — judges see it first.

**B3. The server-side proxy — the one piece that makes the whole hosted/local split work.**

```ts
// app/api/closer/[...path]/route.ts
import { auth } from '@clerk/nextjs/server'

async function forward(req: Request, { params }: { params: { path: string[] } }) {
  const { getToken, userId } = await auth()
  if (!userId) return new Response('unauthorized', { status: 401 })
  const token = await getToken()
  const url = `${process.env.CLOSER_API_BASE}/${params.path.join('/')}${new URL(req.url).search}`
  const res = await fetch(url, {
    method: req.method,
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: req.method === 'GET' ? undefined : await req.text(),
    cache: 'no-store',
  })
  return new Response(res.body, { status: res.status, headers: { 'content-type': 'application/json' } })
}
export const GET = forward, POST = forward, DELETE = forward
```
The browser only ever calls `/api/closer/...` on its own origin. `CLOSER_API_BASE`
(the tunnel) stays a server secret. No CORS, no mixed content, no client rebuild when
the tunnel changes.

**B4. Screens.**

- `/deals` — three groups: **Open**, **Closed**, **Walked**. Card per deal: title,
  state pill, asking, current recommendation, savings (closed), relative time.
  Empty state: "Text a listing link to +1 (205) 261-1117 to start your first deal."
- `/deals/[id]` — the money screen. Belief curve (port the Chart.js logic from
  `static/dashboard.html:87-110`, or redo in Recharts), `R`/`V`/floor reference lines,
  KPI strip (deal likely %, their floor, seller last, your last), big recommendation
  banner colored by action, valuation card with hidden costs + red flags + source links,
  live research trace, conversation feed. Poll `GET /api/closer/api/deals/{id}` every
  1.5s while the deal is active.
- `/deals/new` — paste a listing link → `POST /api/deals`.
- Deal detail composer — paste seller text or upload a screenshot →
  `POST /api/deals/{id}/messages` or `/screenshot`.
- `/settings` — phone linking (`POST /api/me/phone`), shows link status.

**B5. Polish that reads as "product" not "hackathon".** Skeletons on first load, not
spinners. Optimistic append on send. `AWAITING_RESEARCH` renders the live tool trace
streaming in — that is a great 15 seconds of demo. Dark mode default, matching the
existing palette (`#0b0e14` bg, `#5b8cff` accent). Mobile-usable: judges will pull it
up on a phone next to the iMessage thread.

**Lane B gate**: Vercel preview URL, sign in with a Clerk test user, list renders from
fixtures, detail renders a fixture belief curve, no client-side reference to the
tunnel URL anywhere in the bundle.

---

### Lane C — Infra + env (`lane/infra`)

Owner: whoever likes shell. Owns `.env`, scripts, Vercel config.

**C1. Stable tunnel** (chosen in Phase 0) with a supervised restart:
```bash
scripts/tunnel.sh    # exec's ngrok/cloudflared with the fixed hostname, auto-restarts
```

**C2. One-command boot** — `Makefile` at repo root:
```make
dev:      ## backend + tunnel + linq listener, all restart-on-crash
	@scripts/dev.sh
backend:  ; cd closer && .venv/bin/uvicorn app.main:app --port 8000
tunnel:   ; scripts/tunnel.sh
listen:   ; linq webhooks listen --profile closer --forward-to http://localhost:8000/webhooks/linq
health:   ; curl -s localhost:8000/health | jq
demo:     ; scripts/demo_arc.sh
```

**C3. Env matrix** — keep both sides documented in one place:

| Where | Var | Value |
|---|---|---|
| backend `.env` | `RUNWARE_API_KEY`, `LINQ_API_KEY` | set (verified working) |
| backend `.env` | `RESEARCH_MODE` | `live` (flip to `mock` if the network dies) |
| backend `.env` | `CLERK_ISSUER` | `https://<slug>.clerk.accounts.dev` |
| backend `.env` | `CLERK_AUTHORIZED_PARTIES` | `https://closer-dashboard.vercel.app` (+ preview domains) |
| backend `.env` | `DEV_AUTH` | **`false` once Clerk works** — `true` keeps the bypass alive |
| backend `.env` | `CLOSER_STORE_PATH` | `./data` |
| backend `.env` | `LINQ_WEBHOOK_SECRET` | set it — a configured secret auto-enables HMAC verification (`linq.py:98`) |
| Vercel | `CLOSER_API_BASE` | `https://<stable-tunnel-host>` |
| Vercel | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | from Clerk |

**C4. The Clerk ↔ backend handshake, and how to prove it.** The backend verifies
RS256 against Clerk's JWKS, checks `iss`, and — when `CLERK_AUTHORIZED_PARTIES` is set
— requires `azp` to be in the list (`auth.py:59`). A token with **no** `azp` is
rejected. Verify with a real token before Lane B integration:
```bash
# grab a session token from the browser devtools on the deployed dashboard
curl -s https://<tunnel>/api/deals -H "Authorization: Bearer $TOK" | jq
```
Expect `{"deals":[…]}`. If you get `401 unauthorized party`, the Vercel domain is
missing from `CLERK_AUTHORIZED_PARTIES`. If `401 invalid token`, `CLERK_ISSUER` is the
wrong URL (it is the **Frontend API** URL, not the dashboard URL).

**C5. Flip the bypass off.** While `DEV_AUTH=true`, `clerk_enabled()` returns `false`
and **any caller can pass `X-Dev-User: <anything>` and read that user's deals**
(`auth.py:81-86`). That is fine on a laptop and unacceptable once a public Vercel app
points at the tunnel. Flip `DEV_AUTH=false` the moment Clerk verifies, and re-run the
Phase 2 step 9 two-user isolation check.

**Lane C gate**: `make dev` from a clean shell brings up all three processes;
`curl https://<tunnel>/health` works from a phone on cellular; a real Clerk token
returns deals; `X-Dev-User` returns 401 after the flip.

---

### Lane D — Messaging + demo (`lane/messaging`)

Owner: whoever will actually present. Touches no shared source files.

**D1. Live inbound (B5).** Start the listener, text `+12052611117` from your phone,
confirm a reply. On a Shared Line, **the contact must text us first** — inbound-first
is a hard constraint, so the demo always starts with a human text.

**D2. Marcus arc.** `~/seller-agent` (port 8787, `+12054909563`) is the counterparty:
2008 Camry listed $6,400, true value ~$4,200, hidden walk-away $4,750, anchors, quotes
retail comps, deflects KBB, claims fake other buyers. Script and rehearse the exact
5-message arc where Closer calls the `bluff_claim` and the curve refuses to move.
Record it as a GIF for the fallback slide.

**D3. Fixtures.** Three real chat screenshots (Facebook Marketplace, Craigslist email,
plain iMessage) checked into `closer/tests/fixtures/` — Lane A's vision tests use them
and the demo has a guaranteed-good image to drop in.

**D4. `DEMO.md`** — the runbook: exact commands, exact messages to send, what the
screen should show at each beat, and the two failure recoveries (tunnel restart,
`RESEARCH_MODE=mock` flip).

**Lane D gate**: a full iMessage negotiation completes with the dashboard open on a
second screen, both updating live.

---

## 5. Risks, ranked

| Risk | Blast radius | Mitigation |
|---|---|---|
| Tunnel hostname changes | Dashboard goes blind mid-demo | Stable hostname in Phase 0 — this is *why* it is in Phase 0 |
| Laptop sleeps / wifi drops | Whole backend gone | `caffeinate -dimsu make dev`; hotspot as backup; `mock` research needs no network |
| Clerk `azp` mismatch on preview URLs | 401 on every dashboard call | Put the wildcard preview domain in `CLERK_AUTHORIZED_PARTIES` too, or demo from the production alias only |
| Listing sites 403 the research agent | "$0 fair value" on stage | A4 fallback asks for the asking price; `mock` mode as the floor |
| Runware credits exhausted | No classify/draft/vision | Rules-based classifier + heuristic drafts already exist and are tested — verify that path once, deliberately, with the key unset |
| Two people edit `main.py` | Merge hell at hour 5 | §2.4 ownership table |

---

## 6. Definition of done

The MVP is done when a stranger can do this without you touching a keyboard:

1. Open `closer-dashboard.vercel.app`, sign up with Clerk.
2. Link their phone in Settings.
3. Text a real used-car listing link to `+1 (205) 261-1117`.
4. Watch the research trace stream into their dashboard, then get a valuation text back.
5. Relay the seller's replies — by text, by paste, or by screenshot — and get a
   specific number to send, every time.
6. See the belief curve refuse to move when the seller bluffs.
7. Close the deal and see it move to Closed with the dollars saved.
8. Sign out. Nobody else can see any of it.

Steps 3, 5 (screenshot), and 8 are the three that do not work today. Lanes A, B, and C
exist to fix exactly those.
