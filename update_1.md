# Update 1 — Closer is an iMessage agent. That's the whole product.

**Written**: 2026-07-24. Revises the plan of the same name after a live audit of
`main` (`71873a6`) plus a product decision that deletes about a third of it.

**The decision**: there is no dashboard. There is no web app, no Clerk, no
tunnel, no browser. **Closer is a phone number.** Everything a user can do —
start a deal, switch deals, see the belief curve, see lifetime savings, close,
walk — happens in an iMessage thread with the agent.

**Target**: a stranger saves your number, texts it a listing link, and runs
multiple simultaneous car negotiations from Messages, with a Bayesian model of
the seller's price floor rendered back to them as cards in the thread.

**Shape**: 4 phases, 4 parallel lanes, one branch per lane.

---

## 0. What this changes, and what survives

### Gaps that no longer exist (deleted, not deferred)

| Old gap | Why it's gone |
|---|---|
| B2 — no dashboard app | There is no dashboard. Nothing to build. |
| B3 — identity is split (`phone:` vs Clerk `sub`) | `phone:+1205…` **is** the identity now. Nothing to link. |
| B4 — nothing deployed | Nothing needs to be. The backend is a laptop process; the product surface is Apple's. |
| — tunnel, stable hostname, ngrok/cloudflared | `linq webhooks listen --forward-to` streams inbound over an outbound connection. **No public URL anywhere in the system.** |
| — Clerk provisioning, `azp` allow-lists, JWKS, `DEV_AUTH` flip | No JWTs. `app/auth.py` stops being load-bearing. |

That is one entire lane, one entire hosting story, one auth vendor, and the
top-ranked risk in the old plan (tunnel hostname changes mid-demo), removed by a
product decision rather than by engineering.

### Gaps that survive, unchanged

| # | Gap | Detail |
|---|---|---|
| B1 | **Screenshot path 400s** | `app/runware.py:83` sends `images` at task top level → `unsupportedParameter: 'images' … not supported for text inference`. Verified working shape in §7 A1. Screenshots matter *more* now — a screenshot is the most natural thing to send an agent from a phone. |
| B5 | **Inbound iMessage not wired** | No `linq webhooks listen --forward-to` process running. Texting `+12052611117` currently hits nothing. This is now the single point of failure for the entire product. |
| B6 | `RESEARCH_MODE=mock` | `.env` serves the canned Mazda payload; the live agent that works is switched off. |
| B7 | `MemoryStore` | Every deal dies on backend restart. Fatal now — the thread is the only place a user's history lives, and they can't re-derive it. |
| B8 | Live research degrades to $0 | cars.com / autotrader / kbb return HTTP 403. With no asking price parsed, the fallback emits `V=0, R=0` and a "$0 fair value" summary. |
| B9 | Stale process on :8010 | Started before `LINQ_API_KEY` landed in `.env`; reports `linq:false`. Restart it. |

### New gaps this plan creates

| # | Gap | Detail |
|---|---|---|
| N1 | **One deal per phone** | `_resolve_or_create` (`main.py:265`) returns the most recent *active* deal for a sender. A second listing link while a deal is live silently reuses or clobbers. Multi-deal is the core of this update. |
| N2 | **No intent routing** | Every inbound text is treated as a seller relay. "how much have I saved" would be classified as a seller message and fed to the belief engine. |
| N3 | **No cards** | The belief curve exists only as `snapshot.floor_map`, consumed by an HTML canvas nobody will look at. Nothing renders it into a message. |
| N4 | **Linq's rich surface is unused** | We call exactly one endpoint (`POST /chats`). Typing indicators, tapbacks, effects, and attachments — the things that make this feel like an agent and not an SMS bot — are all untouched. |

### Still true (verified against live services, kept from the prior audit)

| Thing | Evidence |
|---|---|
| Bayesian engine | `pytest tests/` → **269 passed** in 0.55s |
| Negotiation loop | Full 4-turn arc through `POST /simulate` with real Claude via Runware |
| Bluff detection | "someone's coming tomorrow, 15 is lowest" → **HOLD**, floor estimate moved $13,931 → $13,940 (barely) |
| Convergence | "14,000 final" → floor $12,942, `p_accept` **85%**; "fine, deal" → CLOSED $13,200, $2,800 under ask |
| Research agent (live) | Real run on a 2008 Camry: DDG search → KBB/Edmunds/CarComplaints, fair value $3,500, 5 hidden costs, 5 red flags, `confidence: med`, sources cited |
| Linq account | `linq doctor --profile closer` → 6/6 pass, token valid, `+12052611117`, 1 webhook active |

---

## 1. One note on the repo constraint, then we move on

`CLAUDE.md` says *"Ship to a live URL. Anything demoable should be deployable
(Vercel preview) at any moment."* This plan deliberately does not, because the
deliverable is a phone number and a URL would be a second, worse copy of it.

The honest substitute, and it is genuinely better for a demo: **a one-page
Vercel landing at `closer.vercel.app` whose only content is the Linq share-link
QR code and a live "$ saved across all deals" counter.** Judges scan it with a
phone camera, Messages opens with the number and a pre-filled draft, and they
are onboarded in one tap. It is ~30 minutes, it is not on the critical path, and
it is Dev 1's last Phase-2 task — after everything else is green. Either of you can skip it
without touching the demo.

---

## 2. Target architecture

```
   Judge's iPhone                     Marcus (seller agent)
   +1 (any number)                       +12054909563
        │                                     │
        │  iMessage                           │ iMessage
        ▼                                     ▼
   ┌─────────────────── Linq ───────────────────┐
   │      Shared Line  +12052611117             │
   └────────────────────┬───────────────────────┘
          message.received │ (~1s)      ▲ send / react / typing / attach
                           ▼            │
              linq webhooks listen --forward-to
                    (your laptop, outbound only)
                           │
                           ▼
              ┌──────────────────────────┐
              │  Closer  localhost:8000  │
              │  FastAPI + numpy         │
              │  ┌────────────────────┐  │
              │  │ intent router      │  │  ← new
              │  │ belief engine      │  │
              │  │ research agent     │  │
              │  │ card renderer      │  │  ← new
              │  └────────────────────┘  │
              │  FileStore ./data/       │  ← new
              └──────────────────────────┘
                           │
                           ▼
                   Runware (all inference)
```

Three properties fall out of this and each one removes a class of demo failure:

**No inbound port.** `linq webhooks listen` holds an outbound connection to Linq
and POSTs to `http://localhost:8000`. There is no tunnel to die, no hostname to
rotate, no TLS, no CORS, no origin allow-list, and no public attack surface.
Hotel wifi with client isolation still works.

**No browser.** Nothing to deploy, nothing to sign into, no session that can
expire on stage, no second screen to keep in sync with the thread.

**The demo surface is Apple's.** For judges, mirror the phone — macOS Sequoia
iPhone Mirroring, or QuickTime → Movie Recording → iPhone as camera source. The
thing on the projector is a real iMessage thread. That is far more convincing
than a dashboard, because everyone in the room already knows what it should look
like and can tell it isn't faked.

**The one new fragility, stated plainly**: if `linq webhooks listen` dies, the
product is silently dead — no error, no 500, texts just vanish. Dev 1 owns
supervision, a `/health/inbound` staleness probe, and a preflight ping. Treat it
with the paranoia previously reserved for the tunnel.

---

## 3. Auth is the phone number

Linq's webhook delivers `data.sender_handle.handle` — the E.164 number Apple
resolved for the sender. It is not a field the user fills in; it comes from the
carrier/Apple side of the connection. So:

```
user_id = "phone:" + normalize_e164(sender_handle)
```

That is the whole auth system. Consequences, all good:

- **No signup.** First text creates the user. The onboarding message *is* the
  account-creation flow.
- **No login, no session, no logout, no password reset, no token refresh.**
- **Isolation is automatic.** Deals are keyed by `user_id`; a different phone
  produces a different `user_id`, and there is no code path that reads across
  them. The old Phase-2 step 9 ("sign in as a second user, see nothing") becomes
  "text from a second phone, see nothing" and is easier to prove.
- **`app/auth.py` and `pyjwt` stay in the tree but stop being load-bearing.**
  The `/api/*` Clerk-authed routes remain for local curl-driven testing and bind
  to `127.0.0.1` only. Do not delete them — the demo runbook uses them to drive
  scripted rehearsals without a phone.

**Trust model, documented as a deliberate choice.** We trust Linq's sender
handle. A SIM swap or a spoofed handle would impersonate a user. For a hackathon
demo of a negotiation coach — where the worst case is someone seeing another
person's car deal — that is the right trade. Write it as a comment in
`_resolve_user`, not as a footnote nobody reads.

**Abuse limits, because there is no signup gate** (Dev 1, Sync 1, ~15 min):
- max 10 deals per phone; the 11th replies "you've got 10 running — close or
  walk one first, or say *delete the Civic*"
- max 20 inbound messages per phone per minute, then a polite throttle reply
- both counters live in the store, both are per-`user_id`, both protect Runware
  credit more than they protect us

**Shared Line reality**: max 20 contacts, and inbound-first. Twenty concurrent
users is the hard ceiling and the demo will use three. Inbound-first is not a
limitation here — it is the signup flow.

---

## 4. Frozen contracts

Lanes only run in parallel if the seams are frozen first. These are the seams.
Paste this section into the team channel before anyone writes code.

### 4.1 The command grammar

The hard rule, and it is the one that makes this work:

> **If a message contains a price, it is a seller relay. Never a command.**

`main.py:109 _detect_outcome` already applies exactly this test for
close/walk detection. Extend it, don't reinvent it. Commands are short, priceless
(literally), and pattern-matched with high precision; **everything that doesn't
match is a relay**, because ~90% of real traffic is "he said 5400" and the cost
of misrouting a relay into a command is a broken negotiation.

Rules first, LLM never. Intent classification must not add a Runware round-trip
to every single seller message — that is latency the demo cannot afford and
credit we shouldn't burn. A leading `/` forces command interpretation as an
escape hatch for the ambiguous cases.

| Intent | Triggers | Effect |
|---|---|---|
| `RELAY` | **default** — anything unmatched, anything with a price, any image | One negotiation turn on the focused deal |
| `NEW` | a URL anywhere in the message | Create a deal, switch focus to it, start research |
| `LIST` | `deals`, `my deals`, `list`, `/deals`, `what am I working on` | Numbered deal list card |
| `SWITCH` | `switch to X`, `go to X`, `X deal`, a bare integer `1`–`10`, `/switch X` | Move focus; confirm with that deal's card |
| `CARD` | `card`, `status`, `where are we`, `show me`, `the curve`, `/card` | Deal card for the focused deal |
| `STATS` | `stats`, `how much have I saved`, `savings`, `total`, `/stats` | Lifetime stats card |
| `CLOSE` | existing `CLOSE_KW` in `main.py:50` | Focused deal → `CLOSED`, confetti, savings |
| `WALK` | existing `WALK_KW` in `main.py:52` | Focused deal → `WALKED` |
| `UNDO` | `undo`, `ignore that`, `scratch that`, `nvm`, `/undo` | Pop the last seller turn, replay, re-recommend |
| `RENAME` | `call this X`, `name it X`, `/name X` | Set `deal.nickname` |
| `DELETE` | `delete X`, `drop X`, `/delete X` | Remove a deal (confirm first) |
| `HELP` | `help`, `?`, `/help`, `what can you do` | Capability card |

Two of these are worth defending:

**`SWITCH` by bare integer** exists because `LIST` returns a numbered list and
the natural reply to a numbered list is a number. It is the cheapest possible
context switch — one character. Guard it: a bare integer is only a switch when
the last outbound message to that user was a `LIST`, otherwise `4200` and `3`
are indistinguishable in intent and one of them is a price. Track
`last_card_kind` per user in the store.

**`UNDO` is nearly free and disproportionately impressive.** `signals_log` is
the source of truth and `Deal.belief()` (`state.py:95`) reconstructs the entire
posterior by replay. Undo = pop the last entry, pop the last two feed turns,
replay, re-recommend. Two lines of real work, and "no wait, ignore that, he
actually said 5,600" is something a person genuinely does mid-negotiation.

`SWITCH` matching order: exact nickname → case-insensitive substring of nickname
→ substring of `title` → list index. Ambiguous match returns the candidates as a
numbered list rather than guessing.

### 4.2 Store protocol — additions (Dev 1 owns, Phase 1)

```python
class Store(Protocol):
    # existing
    def get_deal(self, deal_id) -> Optional[Deal]: ...
    def save_deal(self, deal) -> None: ...
    def list_deals(self, user_id) -> list[Deal]: ...
    def delete_deal(self, deal_id) -> None: ...
    def find_by_chat(self, chat_id) -> Optional[Deal]: ...
    def find_active_by_phone(self, phone) -> Optional[Deal]: ...
    def list_pending_research(self) -> list[Deal]: ...

    # NEW — multi-deal focus + per-user conversation state
    def get_focus(self, user_id: str) -> Optional[str]: ...
    def set_focus(self, user_id: str, deal_id: str) -> None: ...
    def get_user_meta(self, user_id: str) -> dict: ...          # {last_card_kind, last_list, msg_times, onboarded}
    def set_user_meta(self, user_id: str, meta: dict) -> None: ...
```

`find_active_by_phone` stays for the webhook's chat-id fallback, but it is **no
longer** how the focused deal is chosen. Focus is explicit and sticky.

Focus resolution on inbound, in order: explicit `SWITCH` → `get_focus` if that
deal still exists → most recently updated active deal → most recent deal of any
state → none (onboarding).

### 4.3 `Deal` JSON — unchanged, plus two fields

Everything in `deal.public()` (`state.py:108`) stays exactly as it is. Nothing
consumes it over HTTP anymore, but the tests do and the shape is good. Add:

```python
nickname: Optional[str] = None      # user-assigned, wins over `title` in cards
closed_price: Optional[float] = None  # frozen at close; do not recompute later
```

`closed_price` matters: today the close message computes
`last_user_offer or last_seller_price` inline (`main.py:237`) and throws it away.
The stats card sums it across every closed deal, so it has to be persisted at the
moment of close, not re-derived from a log that a later `UNDO` could change.

### 4.4 The floor trajectory — already in the data, no new state

This is the thing the user sees on the deal card: *how the perceived price floor
moved as the deal progressed.* It requires **zero** new persistence.

`_process_seller_turn` (`main.py:201`) already does
`deal.log_turn("closer", coach, recommendation=rec)`, and `rec` from
`BeliefState.recommend()` (`engine.py:556`) already carries every field the card
needs:

```
action  offer  p_accept  ev  zopa  zopa_low  zopa_high  p_close  ceiling
floor_map  floors  floor_point_est  floor_std  asking  R  V
last_seller_price  last_user_offer  turns  rationale
```

So the trajectory is a derivation over `feed`, added to `state.py` (Dev 1, Phase 1):

```python
def trajectory(self) -> list[dict]:
    """Per-turn belief history for the deal card. Derived from the feed —
    every closer turn already carries the full recommendation dict."""
    out = []
    for i, t in enumerate(self.feed):
        if not t.recommendation:
            continue
        prev = self.feed[i - 1] if i else None
        out.append({
            "turn": len(out) + 1,
            "ts": t.ts,
            "floor_est": t.recommendation.get("floor_point_est"),
            "floor_std": t.recommendation.get("floor_std"),
            "seller_price": t.recommendation.get("last_seller_price"),
            "our_offer": t.recommendation.get("offer"),
            "p_accept": t.recommendation.get("p_accept"),
            "action": t.recommendation.get("action"),
            "signals": (prev.signals if prev else None),
        })
    return out
```

Works on deals created before this change. Survives `UNDO` for free, because
`UNDO` truncates the feed. Nothing to migrate.

### 4.5 Savings math — one formula, used everywhere

```
closed:  saved   = asking - closed_price
walked:  avoided = max(0, last_seller_price - V)     # label honestly
open:    projected = asking - snapshot.offer          # never call this "saved"
```

The closed formula is the one the backend already prints in the close message
(`main.py:240`). Do not invent a second one for the stats card. `avoided` on a
walked deal is real but must never be summed into the headline "saved" number —
it gets its own line, phrased as *"walked away from $800 over fair value"*.

### 4.6 Card contracts

Two renderers, same data, built in this order. **The Unicode card ships first**
because it has zero unknowns and the demo is never blocked on it. The PNG card is
an upgrade that lands on top.

`app/cards.py` exposes:

```python
def deal_card(deal: Deal) -> str: ...
def deal_list(deals: list[Deal], focus_id: str | None) -> str: ...
def stats_card(deals: list[Deal]) -> str: ...
def help_card() -> str: ...
def onboarding() -> str: ...
```

`app/render.py` (Dev 2, Phase 2) exposes:

```python
def deal_png(deal: Deal) -> bytes: ...     # matplotlib, Agg backend, 1200x900
def stats_png(deals: list[Deal]) -> bytes: ...
```

**Typography rule for the Unicode cards**: iMessage renders a proportional font.
**Never build columns with spaces** — they will not align on the recipient's
device and the demo will look broken on someone else's phone. `label: value` on
its own line, block-element sparklines (`▁▂▃▄▅▆▇█`), and filled/empty dots
(`●●●●○`) for meters. All three render identically across iOS versions.

**Deal card — the money artifact:**

```
🚗 2008 Camry LE — turn 4 of a live deal
Listed $6,400 · they're at $5,400

Their floor now reads $4,910
Turn 1 it read $6,180 — down $1,270
▇▇▆▅▄▃  turn 1 → 4

Confidence ●●●●○ (±$310)
Zone of agreement $4,600–$5,200

👉 Send $4,750
   68% they take it

🎣 Turn 3 — "three people coming Saturday."
   The curve moved $9. That was a bluff.
```

The last block is the whole pitch in four lines and it must be generated, not
templated: emit it whenever a turn had `bluff_claim=True` **and** the
`floor_est` delta across that turn was under 1% of `asking`. That conjunction is
the product. If no turn qualifies, drop the block — never fake it.

**Deal list:**

```
📋 Your deals

▶ 1. 2008 Camry LE — negotiating, turn 4
     $6,400 ask · send $4,750 next
  2. 2016 Civic EX — researching…
     $11,900 ask
  3. 2014 F-150 XLT — closed 🤝
     saved $2,100

Reply with a number to switch, or say "switch to the Civic".
```

`▶` marks focus. Set `last_card_kind = "list"` and cache the ordering so a bare
integer resolves against exactly what the user saw.

**Stats card:**

```
📊 Closer, all time

💰 $3,940 saved across 2 closed deals
   14% under ask on average

🏆 Best: 2014 F-150 XLT
   $2,100 under ask (18%)

🚶 Walked once — $800 over fair value
📈 5 deals total · 1 live · 6 turns to close on average

You've spent about 11 minutes texting me.
```

That last line is deliberate. "Eleven minutes for $3,940" is the value
proposition stated as a fact about the user's own data, and it is trivially
computable from `created_at`/`updated_at` deltas.

**PNG deal card** (the upgrade): x-axis = turn, primary line = `floor_est` with a
`±floor_std` shaded band, horizontal reference lines at `asking`, `V`, `R`,
seller prices as descending markers, our offers as ascending markers, and a
callout arrow on the bluff turn. Dark background `#0b0e14`, accent `#5b8cff` —
matches the existing palette so the fallback slide and the card look like one
product. Render with matplotlib's `Agg` backend (no display server, already have
numpy). Add `matplotlib>=3.9` to `requirements.txt`; it is the only new dep.

### 4.7 Linq client surface — additions (Dev 2 owns `app/linq.py` in Phase 2)

```python
def send(to, text) -> dict: ...                                   # exists
def send_media(to, text: str | None, file_path: str) -> dict: ... # NEW
def upload_attachment(file_path: str) -> str: ...                 # NEW -> url/id
def react(message_id: str, type: str, emoji: str | None) -> dict: ...  # NEW
def typing(chat_id: str, on: bool) -> dict: ...                   # NEW
def send_effect(to, text, effect: str) -> dict: ...               # NEW
def parse_webhook(body) -> Optional[InboundMessage]: ...          # exists
def parse_reaction(body) -> Optional[InboundReaction]: ...        # NEW
```

**Verified** (documented in `LINQ.md`, exercised via the CLI): the effect,
reaction, typing, and attachment features all exist and are reachable as
`linq messages send --effect`, `linq messages react`, `linq chats typing`, and
`linq attachments upload`.

**Not verified**: their REST shapes on Partner API v3, and whether inbound
tapbacks arrive as a webhook event we can subscribe to. Phase 0 probes both
(§6.0, tasks 3–4). The guaranteed fallback is `subprocess` to the CLI with
`--profile closer` — ugly from FastAPI, works today, and every one of these calls
is fire-and-forget decoration that must never block or fail a negotiation turn.
Wrap every one in `try/except: pass`, exactly like the existing `linq.send`
call sites do.

### 4.8 File ownership (merge-conflict firewall)

The team is **two developers**. Ownership is per-file and it **changes at Sync 1**
— that flip is the single most likely source of a merge conflict, so it is stated
twice and gated.

| Path | Phase 1 | Phase 2 |
|---|---|---|
| `closer/app/main.py` | **Dev 1** | **Dev 2** ← flips |
| `closer/app/state.py`, `store.py`, `runware.py`, `llm.py` | Dev 1 | Dev 1 (frozen after Sync 1) |
| `closer/app/research.py` | Dev 1 | Dev 1 |
| `closer/app/intent.py` *(new)*, `cards.py` *(new)* | **Dev 2** | Dev 2 |
| `closer/app/linq.py`, `render.py` *(new)* | — (stubbed at Sync 1) | **Dev 2** |
| `.env`, `.env.example`, `Makefile`, `scripts/**` | Dev 1 | Dev 1 |
| `closer/tests/**` | Dev 1 owns existing; Dev 2 adds `test_intent.py`, `test_cards.py`, `tests/fixtures/` | same |
| `DEMO.md` | — | Dev 1 |
| `update_1.md`, `LINQ.md`, `README.md` | either, append-only sections | same |
| `closer/static/**`, `closer/app/auth.py`, `demo.py` | nobody touches this update | — |

**Two frozen seams, one per phase boundary.** Both are stub files committed to
`main` *before* the branches diverge, so each dev codes against a signature rather
than against the other person's unwritten code.

*Seam 1 — committed before Phase 1* (`intent.py`, `cards.py`, per §4.1 and §4.6):

```python
# closer/app/intent.py
from dataclasses import dataclass
from typing import Literal, Optional

Kind = Literal["RELAY", "NEW", "LIST", "SWITCH", "CARD", "STATS",
               "CLOSE", "WALK", "UNDO", "RENAME", "DELETE", "HELP"]

@dataclass
class Intent:
    kind: Kind
    target: Optional[str] = None   # SWITCH / RENAME / DELETE argument
    url: Optional[str] = None      # NEW
    text: Optional[str] = None     # RELAY passthrough

def classify(text: Optional[str], *, has_image: bool,
             deals: list, meta: dict) -> Intent:
    """Pure. No I/O, no LLM, no import from main.
    Hard rule: a message containing a price is RELAY, never a command."""
    raise NotImplementedError
```

```python
# closer/app/cards.py
def deal_card(deal) -> str: ...
def deal_list(deals, focus_id: str | None) -> str: ...
def stats_card(deals) -> str: ...
def help_card() -> str: ...
def onboarding() -> str: ...
```

Dev 2 tests `classify` standalone from minute zero. Dev 1 writes the dispatch
against it at Sync 1, before Dev 2's implementation exists.

*Seam 2 — committed at Sync 1* (`linq.py`, per §4.7): `react`, `typing`,
`send_media`, `send_effect` as no-op stubs. Dev 2 fills them in **and wires the
call sites**, which is why `main.py` changes hands.

Two rules keep merges boring: **one file, one owner, one phase**, and **rebase on
`main` before every push**.

---

## 5. Linq, pushed to the max

This is the differentiator. Every other team's agent will send plain text
bubbles. Here is the full inventory of what the platform gives us and what each
one buys, ordered by ratio of demo impact to build time.

### 5.1 Tapbacks as an acknowledgement channel — react before you reply

The problem: research takes ~30s and an LLM turn takes ~3s. In iMessage, three
seconds of nothing feels broken.

The fix costs one API call and is the highest-impact item on this list. The
instant a message lands, before any inference runs, react to it:

| Reaction on the user's message | Means |
|---|---|
| 👍 `like` | Logged it, working |
| ❗ `emphasize` | Bluff detected in that message |
| ❓ `question` | Couldn't parse — a clarifying question is coming |
| ❤️ `love` | That was the message that closed the deal |

The user gets sub-second feedback that the agent is alive and *what it thought*,
before a single token is generated. Nothing else on this list is as cheap.

### 5.2 Tapbacks as an input channel — this is the novel one

If inbound reactions arrive as webhook events (Phase 0 probes this), then the
user tapping back on **our** recommendation is a first-class command:

| User's tapback on our message | Means |
|---|---|
| 👍 `like` | "Sent it" — lock `last_user_offer`, await their reply |
| 👎 `dislike` | "Give me a different number" — re-draft one notch softer |
| ❓ `question` | "Explain" — reply with the math: floor estimate, std, `p_accept`, why |
| ‼️ `emphasize` | "This is the one" — pin the deal to focus |

A two-tap negotiation loop with no typing. No other messaging integration in the
room will do this, and it is maybe 40 lines once the event shape is known. If
inbound reactions turn out not to be deliverable, this section is cut with zero
impact on anything else — nothing depends on it.

### 5.3 Typing indicators — bracket every slow operation

`linq chats typing <chat-id>` on before research / classify / draft, `--stop`
after. Research runs ~30s; a typing bubble for thirty seconds reads as *thinking*
rather than *broken*. `LINQ.md` warns these only surface in chats with recent
activity, which is exactly our situation (the user just texted us).

Pair it with a progress trickle during research — the research agent already
emits `on_step` callbacks (`main.py:131`), so stream two of them into the thread:

```
🔎 Reading the listing…
🔎 Pulling KBB + Edmunds comps…
📍 2008 Camry LE, 142k miles. Fair value $4,200.
   Timing belt's due — that's $900. Full card coming.
```

Three bubbles over thirty seconds beats one bubble after thirty seconds by a
wide margin, and the trace is *already being computed*. We are currently
throwing it away.

### 5.4 Message effects — three per demo, no more

| Effect | Moment |
|---|---|
| `confetti` | Deal closes |
| `fireworks` | New personal-best savings |
| `slam` | `WALK` recommended — the physical thud sells the gravity |

`celebration` on the very first deal a user ever closes. That is the complete
list. A fourth effect turns a product into a toy, and every one of these fires
inside a conversation the user drove.

### 5.5 Attachments — the deal card as a real image

`upload → url → send with a media part`. This is what makes the belief curve
land: a chart of the seller's floor collapsing turn by turn, in an iMessage
bubble, on a projector. Ship the Unicode card first so this is never blocking,
then upgrade.

Watch the account binding — `LINQ.md`: *"attachments are bound to the account
that uploaded them."* Everything here uploads under `closer`. Marcus cannot send
our media and we cannot send his.

### 5.6 The QR share link is the entire signup flow

`linq contacts add +1XXXXXXXXXX --profile closer` prints:

```
https://linqapp.com/s/text/+12052611117?from=+1XXXXXXXXXX&msg=...
```

On mobile that opens Messages with a pre-filled draft. On desktop it renders a
QR code. So the demo's call to action is: **point your camera at this slide, hit
send.** That single link solves inbound-first, replaces account creation, and
lets a judge become a live user in about four seconds without typing a phone
number. Put it on the final slide and on the optional landing page.

### 5.7 Shape the messages like a person, not a server

- **The number gets its own bubble.** `Send $4,750` alone in a message is
  one-tap long-press-copy. Buried in a paragraph it isn't.
- **Two to three short bubbles, never one wall of text.** Reasoning, then the
  number, then the card.
- **No markdown.** iMessage renders none of it. `**bold**` shows up as
  literal asterisks. Emoji are the only formatting that exists.
- **Never send two bubbles under ~400ms apart** — they arrive out of order often
  enough to matter on stage. Small sleep between sends.

### 5.8 Things we could do, and why we're not

- **Group chats** ("loop in your spouse for a second opinion") — Linq supports
  multi-participant chats and it is a genuinely good feature. Cut: routing a
  belief state across two identities is a real design problem, not a two-hour
  one. Stretch only.
- **Proactive nudges** ("he hasn't replied in 3 hours, want to push?") —
  `LINQ.md` is explicit that one-way and notification-only flows risk getting the
  number flagged by Apple. Allowed *only* when the user asked for it in-thread
  ("remind me if he goes quiet"), on a deal they started, once. Build it that way
  or not at all.
- **`linq messages thread`** to rehydrate history after a restart — nice
  insurance, superseded by `FileStore` (A3). Skip.

---

## 6. Phases

Two developers, four blocks. Each build block is ~2 hours per dev and ends on a
gate you can **run as a command** — so both halves finish "on = done" at the same
barrier, with nothing to argue about.

```
Phase 0  ──── together, 45 min ──── inbound proven, probes answered, seams frozen
Phase 1  ──── Dev 1 ‖ Dev 2, ~2h ── engine & state  ‖  intent & cards
Sync 1   ──── together, 30 min ──── dispatch wired. THE PRODUCT EXISTS.
                                    seam 2 frozen · main.py changes hands
Phase 2  ──── Dev 1 ‖ Dev 2, ~2h ── ops & demo      ‖  the message surface
Sync 2   ──── together, 45 min ──── kill drills, offline run, two timed rehearsals
```

### Phase 0 — Setup + probes, 45 minutes, together

Nothing splits until these are green. The probes matter: three of the Linq
features this plan leans on have unverified REST shapes, and finding that out at
hour five is how a demo dies.

1. **Free port 8000 and kill the stale :8010 process** (gap B9 — it has no Linq
   key and reports `linq:false`):
   ```bash
   lsof -nP -iTCP:8000 -sTCP:LISTEN
   lsof -nP -iTCP:8010 -sTCP:LISTEN
   kill <pids>
   ```
2. **Prove inbound end to end.** Two terminals:
   ```bash
   cd closer && .venv/bin/uvicorn app.main:app --port 8000
   linq webhooks listen --profile closer \
        --forward-to http://localhost:8000/webhooks/linq
   ```
   Text `+12052611117` from a phone. You must see the event in the listener AND
   a reply arrive. **This is the single most important gate in the plan** — it is
   gap B5, and nothing else works without it.
3. **Probe the REST shapes** (~15 min, one person, results into the channel):
   ```bash
   linq webhooks events --profile closer        # is there a reaction event?
   linq messages send <chat> --message "x" --effect confetti --json
   linq messages react <message-id> --type like --json
   linq chats typing <chat-id> --profile closer
   linq attachments upload ./static/closer_logo.png --profile closer
   ```
   Run each with `--json` and capture the request/response. If the CLI is
   verbose enough to reveal the HTTP call, write the shapes into `LINQ.md`
   §Command reference. If not, Dev 2 shells out to the CLI in Phase 2 and moves on.
4. **Probe inbound tapbacks.** With `linq webhooks listen` running, tapback a
   message from the phone. Does an event arrive? Capture the JSON. **This single
   observation decides whether §5.2 ships.** If nothing arrives in 10 seconds,
   cut §5.2 and say so out loud — do not investigate further.
5. **Freeze seam 1 and cut the branches.** Commit the `intent.py` / `cards.py`
   stubs from §4.8 to `main` **before** branching. Ten minutes here removes every
   blocking dependency in Phase 1:
   ```bash
   git checkout main && git pull
   git add closer/app/intent.py closer/app/cards.py
   git commit -m "chore: freeze the intent/cards seam"
   git push origin main
   git branch lane/engine   # Dev 1
   git branch lane/agent    # Dev 2
   ```
6. **Read §4 together.** The contract is the coordination mechanism; §4.1 and
   §4.8 are the two that stop you stepping on each other.

**Gate**: a text to `+12052611117` gets a reply from a freshly booted backend
reporting `{"ok":true,…,"linq":true}` on `/health`; the probe results are written
down (§4.7 resolved to verified-or-CLI-fallback); both stub files are on `main`.

---

### Phase 1 — Build the halves blind (~2h each)

Neither dev needs the other's code. Both work against seam 1.

| | **Dev 1 — engine & state** (`lane/engine`) | **Dev 2 — intent & cards** (`lane/agent`) |
|---|---|---|
| Owns | `main.py` `state.py` `store.py` `runware.py` `llm.py` | `intent.py` `cards.py` `tests/fixtures/` |
| 1 | **Vision fix** (§7 A1, ~30 min) — images as Anthropic content parts on the last user message, URLs fetched and base64'd, downscale to 1568px. Unit test per input form. | **Fixture first** (~5 min) — run the existing 4-turn `/simulate` arc, save `/state` output to `tests/fixtures/deal_camry.json`. Build cards against real numbers, not invented ones. |
| 2 | **Multi-deal focus** (§7 A2, ~60 min) — `normalize_e164`, `_resolve_user`, focus + user-meta on all three stores, `_focused_deal` replacing `_resolve_or_create`, `nickname` + `closed_price`. **Delete `main.py:255-262`.** | **`intent.classify`** (§7 B1, ~45 min) — §4.1 grammar, pure, table-driven test with 40+ cases. The one that cannot break: every message containing a price returns `RELAY`. |
| 3 | **`Deal.trajectory()`** (§4.4, ~10 min) — a derivation over `feed`, no new state. Do it early; it is what Dev 2's deal card plots. | **Four Unicode cards** (§4.6, ~45 min) — deal, list, stats, help. `python -m app.cards --demo` renders from the fixture. Then paste each into a real thread and look at it on a phone. |
| 4 | **FileStore** (§7 A3, ~30 min) — JSON per deal under `data/deals/`, atomic write, `CLOSER_STORE_PATH=./data`, `closer/data/` in `.gitignore`. | **Copy** (§7 B3, ~20 min) — onboarding, help, ambiguous switch, throttle, deal-parked, research-blocked. |
| **Done gate** | `pytest -q` green · two links from one phone produce two deals with focus on the second · restart the backend and the deals are still there · `python -m app.llm --vision tests/fixtures/chat1.png` prints a price | `pytest tests/test_intent.py tests/test_cards.py -q` green · `python -m app.cards --demo` prints all four **including the null states** (`snapshot is None`, `research is None`) — that is what a judge sees in the first thirty seconds |

---

### Sync 1 — the product first exists (~30 min, together, Dev 1 driving)

Both rebase on `main` and merge. Then, in one sitting:

1. **Dev 1 writes the dispatch** in `route_message`: one branch per `Intent.kind`,
   each calling `cards.*`. ~20 lines. Written against the signature, so it should
   compile the first time.
2. **Two small things Dev 1 lands while already inside `main.py`**: the
   `/health/inbound` route, and the per-phone limits from §3 (10 deals,
   20 msgs/min).
3. **Run acceptance steps 1–7 and 13** from the block below.
4. **Freeze seam 2** — commit `linq.py` no-op stubs for `react`, `typing`,
   `send_media`, `send_effect` to `main`.

**Ownership flips here. `main.py` goes to Dev 2 for Phase 2 and Dev 1 does not
touch it again.** Dev 1's Phase-2 work is deliberately scoped to `research.py`,
`scripts/`, `Makefile`, and `DEMO.md` so this holds without discipline.

**Gate**: a link creates a second deal, `deals` lists both, `1` switches back, and
a backend restart loses nothing. That is the MVP. Everything after this is polish
that makes it feel like a product.

---

### Phase 2 — Enrich (~2h each)

| | **Dev 1 — ops & demo** (`lane/engine`) | **Dev 2 — the message surface** (`lane/agent`) |
|---|---|---|
| Owns | `research.py` `scripts/` `Makefile` `.env` `DEMO.md` | `linq.py` `main.py` `render.py` `cards.py` |
| 1 | **Supervised listener** (§7 C2, ~30 min) — `scripts/listen.sh`, restart-on-exit with backoff, timestamped log. This is now the top-ranked risk in the plan. | **Linq client** (§4.7, ~40 min) — `react`, `typing`, `send_media`, `send_effect`. Every decorative call `try/except: pass`, never blocking a turn. CLI subprocess is the fallback if the Phase-0 probes didn't resolve the REST shape. |
| 2 | **`make dev` / `make preflight`** (§7 C3, ~30 min) — one-command boot; preflight texts a known contact and asserts a round trip; `make check-profile` asserts `linq whoami --profile closer` returns `+12052611117`. | **Wire typing + tapbacks** (§5.1, §5.3, ~30 min) — react on inbound *before* inference runs, typing bracketing research and every LLM turn, two research-trace bubbles streamed from the existing `on_step` callback. |
| 3 | **Research hardening** (§7 A4, ~30 min) — `RESEARCH_MODE=live`, `User-Agent` on `fetch_page`, 40s wall cap, and the 403 fallback that asks "what are they asking?" instead of emitting `V=0`. | **Effects + attachments** (§5.4, §5.5, ~30 min) — confetti on close, fireworks on a new best, slam on walk. Deal card uploaded and sent as a real image. |
| 4 | **Marcus arc + `DEMO.md`** (§7 D1, D4, ~40 min) — rehearse the five-message bluff sequence against `~/seller-agent`, write the runbook and the three recoveries, generate the QR share link. | **`render.py`** (§4.6, ~40 min) — matplotlib `Agg`, floor line with ±std band, reference lines at asking / V / R, callout on the bluff turn. `#0b0e14` background, `#5b8cff` accent. |
| **Done gate** | `make dev` from a clean shell brings up both processes · kill the listener and it is back inside 5s · `make preflight` green · you can drive the full Marcus arc from the runbook without asking Dev 2 anything | A tapback, a typing indicator, and confetti all visibly land on a real iPhone · `card` returns a PNG chart in the thread · acceptance steps 8–12 pass |

**If you are behind at Sync 1**, cut from Dev 2's Phase 2 in this order: PNG
render → inbound tapbacks (§5.2) → effects → and from Dev 1's, research hardening
(`RESEARCH_MODE=mock` covers the demo). Nothing in Phase 1 is cuttable — that is
the update.

**End-to-end acceptance — the actual MVP definition:**

```
 1. Text "hey" to +12052611117 from a phone that has never texted it
                                     → onboarding message, account exists
 2. Text a Camry listing link        → 👍 tapback, typing, research trace,
                                        valuation card
 3. Marcus texts "6,400 firm, I've got two other people coming"
    Relay it                         → ❗ tapback, coach reply, offer in its
                                        own bubble
 4. Text "card"                      → deal card, floor line + sparkline,
                                        bluff block present
 5. Text a second listing link       → deal 2 created, focus moves,
                                        "deal 1 is parked"
 6. Text "deals"                     → numbered list, ▶ on deal 2
 7. Text "1"                         → focus back to the Camry, card returned
 8. Screenshot a chat, send the image → price extracted, curve updates
 9. Text "undo"                      → last turn removed, previous
                                        recommendation restored
10. Text "we have a deal"            → CLOSED, confetti, "$X under ask"
11. Text "stats"                     → lifetime card, savings correct
12. Repeat step 1 from a second phone → sees NONE of phone 1's deals
13. Restart the backend, text "deals" → everything still there
```

Steps 1–7 and 13 are the **Sync 1** gate. Steps 8–12 are **Dev 2's Phase 2**
gate. Steps 5–7 prove multi-deal, step 9 proves the replay architecture, step 12
proves isolation, and step 13 proves B7 is fixed — the one people forget until
the laptop reboots at the worst possible moment.

---

### Sync 2 — Demo hardening (~45 min, together)

1. **Listener death drill.** Kill `linq webhooks listen` mid-arc. Confirm the
   supervisor restarts it within seconds and the next text lands. This replaces
   the old tunnel drill and it is now the top risk.
2. **Offline rehearsal.** Run the whole arc with wifi off: rules classifier
   (`llm.py:150`) + `RESEARCH_MODE=mock` + Unicode cards must still complete
   every step. Prove it once, deliberately, with `RUNWARE_API_KEY` unset.
3. **Warm start.** `DEMO_MODE=true` pre-seeds a mid-negotiation deal so "stats"
   and "deals" have something to show in the first fifteen seconds.
4. **Two timed rehearsals**, each of you able to drive solo. Whoever did not
   write a half is the one who should drive it.
5. **Fallback slide**: a screenshot of the deal card where the floor line
   flatlines through the bluff turn. If everything else fails, that image is the
   pitch.

---

## 7. Task detail

Reference for the tasks scheduled in §6. Ids are stable — the phase tables point
here rather than repeating themselves.

| Task | Who | When |
|---|---|---|
| A1 vision, A2 focus, A3 FileStore, `trajectory()` | Dev 1 | Phase 1 |
| B1 intent, B2 cards, B3 copy | Dev 2 | Phase 1 |
| A5 dispatch, `/health/inbound`, rate limits | Dev 1 | Sync 1 |
| A4 research, C2 supervisor, C3 boot, D1/D4 demo | Dev 1 | Phase 2 |
| C1 Linq client, B4 render, B5 explain, §5 wiring | Dev 2 | Phase 2 |

### Dev 1 — engine & state (`lane/engine`)

All local, no deploy concerns.

**A1. Fix the screenshot path (B1) — ~30 min, highest value.**

The failing call, verified against the live API:
```
Runware HTTP 400: unsupportedParameter — Unsupported use of 'images' parameter.
This parameter is not supported for text inference.
```
Three shapes probed. Results:

| Shape | Result |
|---|---|
| `task["images"] = [...]` (current) | ❌ `unsupportedParameter` |
| `content: [{type:"image_url", image_url:{url}}]` (OpenAI style) | ❌ `providerBadRequest` from Anthropic |
| `content: [{type:"image", source:{type:"base64", media_type, data}}]` | ✅ **works** — read "$15,200" off a test screenshot |
| `source: {type:"url", url}` | ❌ `providerBadRequest` — **URLs are not accepted** |

Images ride as Anthropic-style content parts on the last user message, and **any
URL — including the Linq media URLs that inbound screenshots arrive as — must be
downloaded and base64'd first.** Patch `runware.py` only; `llm.py` callers keep
passing `images=[...]` unchanged:

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
then in `text_inference`, replacing `task["images"] = images`:
```python
if images:
    last = turns[-1] if turns else {"role": "user", "content": ""}
    text = last["content"] if isinstance(last["content"], str) else ""
    last["content"] = [{"type": "text", "text": text}] + [_image_part(i) for i in images]
    if not turns:
        turns.append(last)
```
Cap the image: Anthropic rejects large payloads and a phone screenshot is 3–5 MB.
Downscale to max 1568px on the long edge before encoding.

Tests: one unit test per input form (data URI / URL / raw base64) asserting the
emitted task JSON against a stubbed `httpx`, plus a live smoke behind an env flag.

**A2. Phone identity + multi-deal focus (N1) — ~60 min, the core of this update.**

- `normalize_e164(handle)` — one helper, used on every read of `sender_handle`.
- `_resolve_user(sender) -> user_id` returning `"phone:+1205…"`, with the trust
  model in a comment.
- Store: `get_focus` / `set_focus` / `get_user_meta` / `set_user_meta` per §4.2,
  in `MemoryStore`, `FileStore`, and `RedisStore` (`SET user:{id}:focus`,
  `SET user:{id}:meta`).
- Rewrite `_resolve_or_create` into `_focused_deal(user_id, chat_id)` using the
  §4.2 resolution order. **A new link never reuses an existing deal** — it always
  creates one and moves focus, and the reply names the deal that got parked.
- Delete the `CLOSED/WALKED` branch at `main.py:255-262` that wipes a finished
  deal's history to reuse the record. Closed deals are the stats card's data;
  destroying them destroys the headline number.
- Add `Deal.nickname` and `Deal.closed_price` (§4.3); set `closed_price` at the
  moment of close, next to the existing under-ask calculation.
- `Deal.trajectory()` per §4.4.
- Rate limits per §3 (10 deals, 20 msgs/min, both per `user_id`).

**A3. FileStore (B7) — ~30 min.**

Backend is local for the whole event, so Upstash is ceremony. Same `Store`
protocol, JSON-per-deal under `data/deals/`, one `data/users/{id}.json` for
focus + meta, atomic write via tmp + `os.replace`, loaded into memory on boot.
`get_store()` selection order: Upstash if configured → `CLOSER_STORE_PATH` if set
→ `MemoryStore`. Default `CLOSER_STORE_PATH=./data` in `.env.example`, and add
`closer/data/` to `.gitignore`.

**A4. Research hardening (B6, B8) — ~30 min.**

- Flip `.env` to `RESEARCH_MODE=live`; keep `mock` documented as the panic switch.
- When the listing fetch 403s **and** no asking price parsed, do not emit
  `V=0/R=0`. Keep the deal in `NEGOTIATING` and have the coach ask: *"cars.com
  blocked me — what are they asking?"* Accept a bare number as `asking`, then
  recompute `V`/`R`. (This is the one place a bare integer is not a `SWITCH`;
  gate it on the deal being in this state.)
- Add a `User-Agent` on `fetch_page` — some 403s are naked-client blocks.
- Cap research wall time at ~40s so a slow crawl never stalls a live thread.

**A5. Wire the router — ~20 min, at Sync 1.**

Against seam 1's frozen signature. One dispatch block in `route_message`, one branch
per intent, each branch calling into `cards.*` and returning a string or a
`(text, png_bytes)` pair. Keep `route_message`'s existing contract so
`/simulate` and the existing tests keep working — the demo runbook drives
rehearsals through it.

**Dev 1, Phase 1 gate**
```bash
pytest tests/ -q                                     # all green, 285+
curl -s localhost:8000/health | jq                   # runware/linq true, FileStore
python -m app.llm --vision tests/fixtures/chat1.png  # prints extracted price
# two links from one phone -> two deals, focus on the second
```

---

### Dev 2 — intent, cards & the message surface (`lane/agent`)

Owner: best writer on the team. This half is *product*. In Phase 1 it never
imports `main` and is blocked by nothing — build against a fixture `Deal` loaded
from JSON. In Phase 2 it takes `main.py` and owns every call site that touches
the thread.

**B1. `app/intent.py`** — §4.1 exactly. Pure, no I/O, no LLM, fully unit-tested.
The test that matters most: **every message containing a price classifies as
`RELAY`**, including `"stats say 5000"` and `"switch to 4200"`. Table-drive it
with 40+ cases. This function is where a broken demo would come from.

**B2. `app/cards.py`** — the four Unicode cards from §4.6. Ship this before
touching PNG. `python -m app.cards --demo` prints all four from fixtures so the
team can read them in a terminal and, more importantly, paste them into a real
iMessage thread and see how they actually render.

**B3. All user-facing copy.** Onboarding, help, ambiguous-switch, throttle,
deal-parked, research-blocked, error states. Voice: a sharp friend who has done
this a hundred times. Short. Specific numbers, never ranges. Never apologize.
Never say "I'm an AI".

```
Onboarding:
  I'm Closer. Send me a used-car listing and I'll tell you what it's
  actually worth, then coach every counter until you're done.

  Text me a link to start. Say "help" for the rest.
```

**B4. `app/render.py`** *(Phase 2)* — the PNG cards per §4.6, matplotlib `Agg`.
Only after B1–B3 are green.

**B5. Explanations on demand** *(Phase 2)*. The `❓` tapback and the word "why" both hit one
function: turn the current `snapshot` into three sentences of plain English
about the floor estimate, its spread, and `p_accept`. `rationale` from
`engine.py:556` is already most of this — extend it, don't duplicate it.

**Dev 2, Phase 1 gate**: all four cards render from fixtures, including the null states
(`snapshot is None`, `research is None`) that a judge sees in the first thirty
seconds; intent table tests green; every card pasted into a real thread and
visually checked on an actual iPhone.

---

### Phase 2 — Linq maximalism + ops (split across both)

**C1 is Dev 2** (`app/linq.py` + the `main.py` call sites). **C2–C5 are Dev 1**
(`.env`, `scripts/`, `Makefile`) — deliberately disjoint files, so the ownership
flip at Sync 1 holds without anyone having to remember it.

**C1. Client surface** *(Dev 2)* — §4.7. Every decorative call (`react`, `typing`,
`effect`) is fire-and-forget: wrapped in `try/except: pass`, never awaited on the
critical path, never able to fail a turn. Attachments and sends are not
decorative and do surface errors.

**C2. Supervised inbound — the new single point of failure.**
```bash
scripts/listen.sh   # exec's `linq webhooks listen --profile closer
                    #   --forward-to http://localhost:8000/webhooks/linq`
                    # restart-on-exit with backoff, timestamped log
```
Plus `/health/inbound` → `{"last_event_age_s": 12.4, "events": 87}`, and a
`make preflight` that texts a known contact and asserts a round trip. If
`last_event_age_s` exceeds 300 during a demo, the listener is dead.

**C3. One-command boot** — `Makefile` at repo root:
```make
dev:        ## backend + supervised listener, restart on crash
	@scripts/dev.sh
backend:    ; cd closer && .venv/bin/uvicorn app.main:app --port 8000
listen:     ; scripts/listen.sh
health:     ; curl -s localhost:8000/health | jq
inbound:    ; curl -s localhost:8000/health/inbound | jq
preflight:  ; scripts/preflight.sh
demo:       ; scripts/demo_arc.sh
```

**C4. Env matrix** — much shorter than it used to be:

| Var | Value |
|---|---|
| `RUNWARE_API_KEY` | set (verified working) |
| `LINQ_API_KEY` | set (verified working) |
| `LINQ_FROM_NUMBER` | `+12052611117` — **explicit, never read from `~/.linq/config.json`** |
| `RESEARCH_MODE` | `live` (flip to `mock` if the network dies) |
| `CLOSER_STORE_PATH` | `./data` |
| `LINQ_WEBHOOK_SECRET` | set it — a configured secret auto-enables HMAC (`linq.py:98`) |
| `DEMO_MODE` | `false` until Sync 2 |

Delete `CLERK_*`, `DEV_AUTH`, `CORS_ORIGINS`, and `UPSTASH_*` from `.env` (leave
them commented in `.env.example` — the code paths still exist and still pass
their tests, they just aren't configured).

**C5. Profile discipline.** Every `linq` invocation in every script carries
`--profile closer`. `~/.linq/config.json` holds one active profile shared by
every process on this machine, and `linq profile use seller` in any terminal
silently repoints anything that relies on the default — no error, wrong line.
Add a `make check-profile` that asserts `linq whoami --profile closer` returns
`+12052611117` and wire it into `dev`.

**Phase 2 ops gate (Dev 1)**: `make dev` from a clean shell brings up both
processes; killing the listener auto-restarts it inside 5s; `make preflight` is
green. **Phase 2 surface gate (Dev 2)**: a typing indicator, a tapback, and a
confetti effect all visibly land on a real iPhone, and `card` returns a PNG.

---

### Dev 1 — demo (Phase 2, `lane/engine`)

Whoever presents should own this. Touches no shared source.

**D1. Marcus arc.** `~/seller-agent` (port 8787, `+12054909563`): 2008 Camry LE
listed $6,400, true value ~$4,200, hidden walk-away $4,750. He anchors, concedes
in shrinking steps, quotes retail listing comps while deflecting KBB, and claims
other interested buyers when there are none — which is exactly the `bluff_claim`
signal the engine is built to catch. Script and rehearse the exact five-message
arc where Closer calls the bluff and the floor line refuses to move. Record it as
a GIF.

**D2. A second deal that exists only to be switched to.** Multi-deal is a headline
feature and it needs two deals on screen. Pre-seed a 2016 Civic mid-research so
"deals" returns a list with real variety in state.

**D3. Fixtures.** Three real chat screenshots — Facebook Marketplace, Craigslist
email, plain iMessage — in `closer/tests/fixtures/`. A1's vision tests use them
and the demo has a guaranteed-good image to send. **Do this in Phase 0** — Dev 1
needs one at hour zero.

**D4. `DEMO.md`** — the runbook: exact commands, exact messages to send in order,
what should appear after each, and the three recoveries (listener restart,
`RESEARCH_MODE=mock`, Unicode cards instead of PNG).

**D5. The QR slide.** Generate the share link with
`linq contacts add <judge-phone> --profile closer`, put the QR on the final
slide, and rehearse handing the phone over. A judge texting the number live is
the strongest possible close.

**D6. Optional landing page** (§1) — only after D1–D5 are green.

**Demo gate**: a full negotiation runs on a real phone, mirrored to a screen,
with a second deal switched to and back, in under four minutes, driven by someone
who did not write the code.

---

## 8. Risks, ranked

| Risk | Blast radius | Mitigation |
|---|---|---|
| `linq webhooks listen` dies | **Product is silently dead.** No error, texts vanish | C2: supervisor + `/health/inbound` + preflight. Rehearse the kill in Sync 2 |
| Laptop sleeps / wifi drops | Backend gone | `caffeinate -dimsu make dev`; hotspot backup; `mock` research needs no network |
| Intent router misreads a seller message as a command | Negotiation turn lost mid-demo | §4.1 price-beats-command rule; 40+ case table test; default is always `RELAY` |
| Linq reaction/typing/attachment REST shapes differ from the CLI | §5.1–5.5 don't ship | Phase 0 probes them *before* lane work; CLI subprocess is the fallback; all of it is decoration wrapped in `try/except` |
| Inbound tapbacks aren't a subscribable event | §5.2 cut | Nothing depends on it. Decided in Phase 0 task 4, in ten seconds |
| Listing sites 403 the research agent | "$0 fair value" on stage | A4 fallback asks for the asking price; `mock` mode as the floor |
| Runware credits exhausted | No classify/draft/vision | Rules classifier (`llm.py:150`) + heuristic drafts already exist and are tested — prove that path once, deliberately, with the key unset |
| Shared Line 20-contact cap | Can't onboard more judges | Remove test contacts before demoing; a paid dedicated line is available from the Linq dashboard if it matters |
| Both devs edit `main.py` | Merge hell at hour 5 | §4.8: exactly one owner per file per phase. Dev 1 in Phase 1, Dev 2 in Phase 2, never both |
| The Sync-1 ownership flip is forgotten | Dev 1 keeps editing `main.py` into Phase 2 | Dev 1's Phase-2 scope is `research.py` + `scripts/` + `DEMO.md` — disjoint by construction, so it holds without discipline |
| One dev finishes their phase well ahead of the other | The fast one starts Phase 2 early and breaks the seam | Gates are commands, not opinions. Finish early → write tests, or pair on the other half's gate. Do not start Phase 2 before Sync 1 |
| Unicode cards misalign on someone else's phone | Looks broken on the judge's device | §4.6 typography rule: no space-aligned columns, ever. Verify on a second physical phone in Phase 1 |

---

## 9. Definition of done

A stranger, on their own phone, without you touching anything:

1. Scans the QR on the slide. Messages opens with the number and a draft. Sends.
2. Gets a reply that explains what Closer does in two sentences.
3. Texts a real used-car listing link. Sees a 👍 tapback immediately, a typing
   indicator, the research trace streaming in, then a valuation with sources.
4. Relays what the seller said — typed, pasted, or screenshotted — and gets one
   specific number to send back, every time, in its own bubble.
5. Texts "card" and sees the seller's floor estimate move turn by turn, and sees
   the turn where it *didn't* move because the seller was bluffing.
6. Texts a second listing link, and now has two deals.
7. Texts "deals", replies "1", and is back on the first one with no state lost.
8. Texts "we have a deal". Confetti. A dollar figure under ask.
9. Texts "stats" and sees every dollar they've saved, all time.
10. Hands the phone to the person next to them, who texts the same number and
    sees absolutely none of it.

There is no eleventh step where they open a website.
