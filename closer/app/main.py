"""Closer — FastAPI orchestrator (Phase 3).

Wires the pieces into one agent:

  create a deal  ─ dashboard POST /api/deals, or the user texts a listing link
  research it    ─ app.research runs an agentic valuation (sets asking / R / V)
  negotiate      ─ each seller reply (iMessage or dashboard) → classify → belief
                   update → recommend → draft → reply, streaming to the dashboard
  manage deals   ─ Clerk-authed CRUD over a per-user Store

Entry points that all funnel through one router:
  POST /webhooks/linq          inbound iMessage (Linq)         — routes by deal state
  POST /simulate               keyboard demo, no phone needed  — same router, send=False
  POST /api/deals ...          dashboard CRUD (Clerk-authed)
  GET  /state                  belief curve + feed for the dashboard
  GET  /                       serves the bundled fallback dashboard
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()  # must precede app.* imports — they read env at module load

import asyncio  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import cards, demo, intent, linq, llm, render, research, runware  # noqa: E402
from app import screenshot  # noqa: E402
from app import store as store_mod  # noqa: E402
from app.auth import DEV_USER_ID, clerk_enabled, require_user  # noqa: E402
from app.state import Deal, DealState, user_id_for  # noqa: E402

STORE = store_mod.get_store()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")
# §5.5 — the deal card as a real chart in the bubble. On by default; the kill
# switch exists because this is the one decoration that costs a network round
# trip on the critical path, and a demo needs a way out that isn't a code edit.
PNG_CARDS = os.getenv("PNG_CARDS", "true").lower() not in ("0", "false", "no")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]

URL_RE = re.compile(r"https?://\S+")

# §3 abuse limits. There is no signup gate, so these are the only gate — and
# they protect Runware credit more than they protect us. Both counters are
# per-`user_id` and both live in the store, so a restart does not reset them.
MAX_ACTIVE_DEALS = 10
MAX_INBOUND_PER_MINUTE = 20
RATE_WINDOW = 60.0

# A listener that has died is a silent outage: texts vanish with no error. The
# webhook stamps every event it receives, `/health/inbound` reports the age, and
# a supervisor (or a human) treats "stale" as "restart `linq webhooks listen`".
INBOUND_STALE_SECONDS = float(os.getenv("INBOUND_STALE_SECONDS", "900"))
_INBOUND = {"events": 0, "messages": 0, "ignored": 0, "reactions": 0,
            "last_event_ts": None, "last_message_ts": None, "last_sender": None,
            "started_at": time.time()}

app = FastAPI(title="Closer API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ── small helpers ────────────────────────────────────────────────────────────
def _find_url(text: Optional[str]) -> Optional[str]:
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


def _starts_a_deal(text: Optional[str], *, has_image: bool = False) -> bool:
    """Does this message name a car we don't have a deal for yet?

    True for a listing link and for a car described in words ("2008 Toyota
    Camry LE, 128k, asking $6,400"). Kept in exactly one place because three
    call sites have to agree on it — `_inbound_deal` picks the deal, the webhook
    enforces the deal cap against it, and `intent.classify` routes on it. Two of
    those disagreeing means a deal researched onto the wrong car.

    An image never starts a deal on its own (§4.1 — an image is evidence about a
    seller), unless it carries a link, which `intent.classify` handles itself.
    """
    if _find_url(text):
        return True
    return not has_image and intent.vehicle_description(text) is not None


def _opening_offer(deal: Deal) -> float:
    if deal.last_user_offer is not None:
        return float(deal.last_user_offer)
    return round(0.75 * deal.asking, 2) if deal.asking else 0.0


def _title_from(payload: dict) -> str:
    f = payload.get("facts") or {}
    parts = [str(f.get(k)) for k in ("year", "make", "model", "trim") if f.get(k)]
    return " ".join(parts).strip() or "Used car deal"


def _expert_for_draft(deal: Deal) -> dict:
    r = deal.research or {}
    return {"fair_value": deal.V, "V": deal.V, "R": deal.R,
            "hidden_costs": r.get("hidden_costs"), "red_flags": r.get("red_flags"),
            "facts": r.get("facts")}


def _snapshot(deal: Deal, rec: dict, coach: str) -> dict:
    return {**rec, "floor_map": _floor_map(rec),
            "asking": deal.asking, "R": deal.R, "V": deal.V,
            "last_seller_price": deal.last_seller_price,
            "last_user_offer": deal.last_user_offer, "coach_message": coach}


def _floor_map(rec: dict) -> dict:
    """Reshape the engine's belief curve into the dashboard's chart contract.

    The engine returns the posterior and its support as two flat lists
    (`floor_map`, `floors`); static/dashboard.html reads `floor_map.floors` and
    `floor_map.p`. Adapting here keeps the engine free of view concerns and the
    chart free of engine internals. Rounded because the snapshot is persisted
    and replayed to the browser on every poll.
    """
    fm = rec.get("floor_map")
    if isinstance(fm, dict):                      # already in chart shape
        return fm
    return {"floors": [round(float(x), 2) for x in (rec.get("floors") or [])],
            "p": [round(float(x), 6) for x in (fm or [])]}


def _awaiting_asking(deal: Deal) -> bool:
    """§7 A4: the listing 403'd and we asked "what are they asking?".

    The one documented case where a bare integer is NOT a list index — so it is
    read off the deal and handed to `intent.classify`. `research.py` sets the
    marker when it lands A4; until then this is always False and the grammar
    behaves exactly as §4.1 describes.
    """
    return bool((deal.research or {}).get("blocked"))


# ── research kickoff (background thread on a long-running host; the /tasks cron
#    is the serverless fallback) ───────────────────────────────────────────────
# §5.3: research runs ~30s. Three bubbles over thirty seconds beats one bubble
# after thirty seconds by a wide margin, and the trace is already being computed
# — we were throwing it away. Two is the cap: the trace emits a dozen steps and
# a dozen bubbles is a spammer, not a coach.
RESEARCH_TRACE_BUBBLES = 2


def _do_research(deal_id: str, link: str, description: str = "") -> None:
    deal = STORE.get_deal(deal_id)
    if not deal or deal.state != DealState.AWAITING_RESEARCH:
        return

    streamed: list[str] = []

    def on_step(step: dict) -> None:
        d = STORE.get_deal(deal_id)
        if d and d.state == DealState.AWAITING_RESEARCH:
            d.research_steps.append(step)
            STORE.save_deal(d)
        # Stream the first couple of notes into the thread as they happen.
        # Decorative and best-effort: a failed trace bubble must never stop the
        # research it is narrating.
        note = (step or {}).get("note")
        if note and len(streamed) < RESEARCH_TRACE_BUBBLES and deal.phone:
            streamed.append(note)
            _send_now(deal.phone, f"🔎 {note}")

    with linq.typing_while(deal.chat_id):
        payload = research.run_research(link, asking=deal.asking,
                                        description=description, on_step=on_step)
    d = STORE.get_deal(deal_id)
    if not d or d.state != DealState.AWAITING_RESEARCH:
        return
    val = research.to_valuation(payload, deal.asking)
    d.asking, d.V, d.R = val["asking"] or None, val["V"] or None, val["R"] or None
    d.research = payload
    d.research_steps = payload.get("steps", d.research_steps)
    d.title = _title_from(payload)
    d.state = DealState.NEGOTIATING
    STORE.save_deal(d)
    if d.phone and linq.available():
        try:
            linq.send(d.phone, research.research_summary(payload))
        except Exception:
            pass


def _start_research(deal: Deal, link: Optional[str], *, background: bool,
                    description: str = "") -> None:
    """Kick research off for a deal identified by a link, a description, or both.

    Exactly one of the two is the norm: a link when the buyer pasted one, a
    description when they just told us what the car is (§4.1 NEW). The deal
    records whichever it got, and `_real_deals` counts either as a real deal.
    """
    deal.listing_link = link or None
    deal.listing_desc = (description or "").strip() or None
    deal.state = DealState.AWAITING_RESEARCH
    deal.research_steps = []
    STORE.save_deal(deal)
    args = (deal.id, link or "", deal.listing_desc or "")
    if background:
        threading.Thread(target=_do_research, args=args, daemon=True).start()
    else:
        _do_research(*args)


# ── one negotiation turn (seller message → coach message) ────────────────────
def _process_seller_lines(deal: Deal, lines: list[str]) -> Optional[str]:
    """Replay one or more seller messages and return the coach's reply.

    A typed relay is one line. A screenshot of a thread is several, and each of
    them is a separate thing the seller did — so each gets its own classify, its
    own belief update and its own point on the curve. Collapsing them into one
    blob (what the first cut did) threw away the shape of the concession, which
    is the only thing the posterior actually reads.

    The user gets ONE coach message regardless: advice on a message they have
    already read the answer to is noise. Intermediate turns are logged with
    `cards.replayed_turn`, whose text is derived from the recommendation and
    never drafted — see that function for why that matters.

    Returns None when there is nothing to replay or no belief to replay it into
    (research hasn't landed), which callers turn into `cards.unparsed()`.
    """
    asking = deal.asking or 16000.0
    lines = [ln.strip() for ln in lines if ln and ln.strip()]
    if not lines or deal.belief() is None:
        return None

    coach = ""
    rec: dict = {}
    for i, line in enumerate(lines):
        sig = llm.classify_seller_message(line, deal.last_seller_price, asking)
        deal.signals_log.append(sig.as_dict())
        if sig.seller_price is not None:
            deal.last_seller_price = sig.seller_price

        belief = deal.belief()
        if belief is None:                         # pragma: no cover - defensive
            return None
        rec = belief.recommend(last_user_offer=_opening_offer(deal),
                               last_seller_price=deal.last_seller_price)
        if i == len(lines) - 1:
            coach = llm.draft_coach_message(
                rec, sig, _expert_for_draft(deal),
                {"last_seller_price": deal.last_seller_price,
                 "last_user_offer": deal.last_user_offer})
        else:
            coach = cards.replayed_turn(rec)

        if rec["action"] == "COUNTER":
            deal.last_user_offer = rec["offer"]    # thread the next offer forward

        deal.log_turn("seller", line, signals=sig.as_dict())
        deal.log_turn("closer", coach, recommendation=rec)

    deal.snapshot = _snapshot(deal, rec, coach)
    return coach


def _process_seller_turn(deal: Deal, seller_text: Optional[str],
                         image_ref: Optional[str]) -> Optional[str]:
    """Single-message compatibility shim over `_process_seller_lines`.

    Kept because `/api/deals/{id}/messages` and the demo runbook still hand us
    one text and at most one image ref.
    """
    if image_ref:
        read = screenshot.read([image_ref], caption=seller_text,
                               seen=deal.seen_screenshot_lines)
        if read.has_new_lines():
            deal.seen_screenshot_lines = screenshot.remember(
                deal.seen_screenshot_lines, read.fingerprints())
            return _process_seller_lines(deal, read.seller_lines)
    return _process_seller_lines(deal, [seller_text] if seller_text else [])


# ── UNDO (§4.1) ──────────────────────────────────────────────────────────────
def _undo(deal: Deal) -> bool:
    """Pop the last seller turn and replay. Returns False if there is none.

    `signals_log` is the source of truth and `Deal.belief()` reconstructs the
    posterior from it, so undo is: drop the last signal, drop the turns it
    produced, and restore the recommendation that was live before it. The
    previous turn's `recommendation` IS that replay — it was computed from
    exactly the signals that remain — so it is restored verbatim rather than
    recomputed against a threaded offer that has since moved on.
    """
    if not deal.signals_log:
        return False
    deal.signals_log.pop()
    while deal.feed and deal.feed[-1].role != "seller":
        deal.feed.pop()                                # the coach reply, plus any chatter
    if deal.feed:
        deal.feed.pop()                                # the seller turn itself

    prices = [s.get("seller_price") for s in deal.signals_log
              if s.get("seller_price") is not None]
    deal.last_seller_price = float(prices[-1]) if prices else None

    # Re-thread the offer exactly the way `_process_seller_turn` threads it
    # forward: the last COUNTER among the surviving recommendations.
    recs = [t.recommendation for t in deal.feed if t.recommendation]
    offer = None
    for rec in recs:
        if rec.get("action") == "COUNTER":
            offer = rec.get("offer")
    deal.last_user_offer = offer

    if recs:
        coach = next((t.text for t in reversed(deal.feed) if t.role == "closer"), "")
        deal.snapshot = _snapshot(deal, recs[-1], coach)
    else:
        deal.snapshot = None
    return True


# ── the router (shared by webhook / simulate) ────────────────────────────────
def _real_deals(user_id: str) -> list[Deal]:
    """Deals worth showing the user.

    A first text from a new phone creates an empty shell (`_inbound_deal`) so
    onboarding has something to hang on. It is not a deal until it has a link
    or a turn, and listing it as one makes "deals" lie on message one.

    Ordered oldest-first, deliberately against the store's recency sort. The
    list card's numbers ARE the switch grammar (§4.1), and a number that means
    a different car depending on which deal you last touched is a trap in a
    medium with no undo — "1" is your first deal, permanently.
    """
    deals = [d for d in STORE.list_deals(user_id)
             if d.listing_link or d.listing_desc or d.feed]
    return sorted(deals, key=lambda d: d.created_at)


def _switch_pool(user_id: str, meta: dict) -> list[Deal]:
    """Deals in the order the user last saw them.

    `resolve_switch`'s index tier resolves against the ordering of the last LIST
    card, so "1" means what it looked like it meant — not what the most-recent
    sort happens to say a minute later.
    """
    deals = _real_deals(user_id)
    ids = meta.get("last_list") or []
    if not ids:
        return deals
    by_id = {d.id: d for d in deals}
    ordered = [by_id[i] for i in ids if i in by_id]
    seen = {d.id for d in ordered}
    return ordered + [d for d in deals if d.id not in seen]


def _start_new_deal(deal: Deal, url: Optional[str], *, parked: Optional[Deal],
                    research_bg: bool,
                    description: str = "") -> tuple[str, Optional[str], Optional[list]]:
    """A listing link ALWAYS starts a deal and takes focus (§7 A2).

    So does a car the buyer described in words but could not link — the research
    agent values either (`research.run_research`), so the grammar treats them the
    same. `url` and `description` are the two ways to name a car; at least one
    must be present or there is nothing to research.

    The webhook path has already done this in `_inbound_deal` and hands the new
    shell straight through; every other caller (`/simulate`, the demo runbook)
    arrives with a deal that may already be running, so the split happens here
    too. One rule, two entry points, no way to fold a link into a live deal.
    """
    description = (description or "").strip()
    if not url and not description:
        return cards.not_negotiating(deal), None, None

    target = deal
    if deal.listing_link or deal.listing_desc or deal.state is not DealState.AWAITING_LINK:
        parked = parked or (deal if deal.is_active() else None)
        target = _new_deal(deal.user_id, deal.chat_id, deal.phone)
    else:
        STORE.set_focus(deal.user_id, deal.id)

    # Log the acknowledgement BEFORE kicking research off. `_do_research` — on a
    # thread or inline — reloads the deal from the store and writes the valuation
    # back, so anything saved from this stale reference afterwards silently
    # overwrites it. Mock research finishes in microseconds and loses that race
    # every time; live research loses it whenever a page is cached.
    msg = (cards.deal_parked(target, parked) if parked is not None
           else cards.research_started(url, description=description))
    target.log_turn("closer", msg)
    STORE.save_deal(target)
    _start_research(target, url, background=research_bg, description=description)
    return msg, None, None


def _asking_from_text(text: Optional[str]) -> Optional[float]:
    """The price in a reply to "what are they asking?" (§7 A4).

    `intent.parse_price` covers everything with three or more digits. The gap it
    leaves is the answer people actually send — "6", "6.4" — which the grammar
    reads as thousands everywhere else, so it is read as thousands here too.
    """
    price = intent.parse_price(text)
    if price is not None:
        return price
    m = re.fullmatch(r"\$?\s*(\d{1,2}(?:\.\d+)?)\s*[kK]?", (text or "").strip())
    return float(m.group(1)) * 1000 if m else None


def _unblock_with_asking(deal: Deal, asking: Optional[float]) -> bool:
    """Turn a `blocked` deal into a live one using an asking price (§7 A4).

    `research.recompute_with_asking` has always existed for this; until now
    nothing called it, so a 403'd listing asked "what are they asking?" and then
    had no way to use the answer. Returns False when there is nothing to unblock
    or the number is not a plausible price.
    """
    if not asking or asking <= 0 or not _awaiting_asking(deal):
        return False
    payload = research.recompute_with_asking(deal.research or {}, float(asking))
    val = research.to_valuation(payload, float(asking))
    deal.research = payload
    deal.asking, deal.V, deal.R = val["asking"], val["V"], val["R"]
    deal.state = DealState.NEGOTIATING
    STORE.save_deal(deal)
    return True


def _seed_deal_from_screenshot(deal: Deal, read: "screenshot.ScreenshotRead") -> bool:
    """Start a deal from a screenshot when there is no listing link to research.

    The honest cheap path: a price and a car name off the image, run through the
    same haircut §7 A4 uses when a listing 403s. `cards.screenshot_started_deal`
    says out loud that this is a rule of thumb rather than research, and a link
    sent later still starts a proper deal.
    """
    asking = read.price_hint()
    if not asking or asking <= 0:
        return False
    payload = research.valuation_from_asking(
        float(asking), title=read.title,
        source="your screenshot" if read.kind == "chat" else "the listing screenshot")
    val = research.to_valuation(payload, float(asking))
    deal.research = payload
    deal.asking, deal.V, deal.R = val["asking"], val["V"], val["R"]
    deal.title = read.title or _title_from(payload) or deal.title
    deal.state = DealState.NEGOTIATING
    STORE.save_deal(deal)
    return True


def _relay_screenshot(deal: Deal, caption: Optional[str],
                      media: list[str]) -> tuple[str, Optional[str], None]:
    """A screenshot of the chat with the seller — the §7 A1 path.

    Ladder, strictly in this order:

      1. Read every image. If none of them read, fall back to the caption as a
         typed relay — "he said 5400 [photo]" must still work when the photo is
         a blurry crop — and only then admit we couldn't read it.
      2. If this deal has no valuation yet, try to seed one from the screenshot
         (an asking price, or the seller's own number) so a user who never had a
         listing link is not stuck.
      3. Replay every seller line the deal has not already seen.

    A screenshot never becomes a command: `intent.classify` sends every image to
    RELAY (§4.1), so "why" written on a photo is still evidence about a seller.
    """
    read = screenshot.read(media, caption=caption, seen=deal.seen_screenshot_lines)

    if not read.ok():
        # The caption is the fallback, not the failure message. A user who typed
        # what was said AND attached the proof should get a real turn out of it.
        if caption and deal.state is DealState.NEGOTIATING:
            coach = _process_seller_lines(deal, [caption])
            if coach:
                STORE.save_deal(deal)
                return coach, None, None
        return cards.screenshot_unreadable(bool(caption)), None, None

    if deal.state is DealState.AWAITING_RESEARCH:
        return cards.not_negotiating(deal), None, None

    seeded = False
    if _awaiting_asking(deal):
        seeded = _unblock_with_asking(deal, read.price_hint())
    elif deal.state is not DealState.NEGOTIATING:
        if deal.state in (DealState.CLOSED, DealState.WALKED):
            return cards.not_negotiating(deal), None, None
        # A screenshot of the LISTING itself names the car, and `run_research`
        # now takes a description as readily as a URL — so that is real research,
        # not a haircut, and it is worth the ~30s because there are no seller
        # messages waiting on an answer. A screenshot of the CHAT is the other
        # case: something IS waiting on an answer, so it takes the cheap seed and
        # gets a number now.
        if read.kind == "listing" and read.title and read.price_hint():
            desc = f"{read.title}, asking ${read.price_hint():,.0f}"
            deal.asking = float(read.price_hint())
            deal.title = read.title
            msg = cards.research_started(desc)
            deal.log_turn("closer", msg)
            _start_research(deal, None, background=True, description=desc)
            return msg, None, None
        seeded = _seed_deal_from_screenshot(deal, read)
        if not seeded:
            return cards.screenshot_needs_a_price(), None, None

    if not read.has_new_lines():
        if seeded:
            STORE.save_deal(deal)
            return cards.screenshot_started_deal(deal), "deal", None
        return cards.screenshot_nothing_new(), None, None

    before = len(deal.trajectory())
    coach = _process_seller_lines(deal, read.seller_lines)
    # Recorded whether or not the replay produced advice: a line we read and
    # could not act on is still a line we must not read again.
    deal.seen_screenshot_lines = screenshot.remember(deal.seen_screenshot_lines,
                                                     read.fingerprints())
    STORE.save_deal(deal)
    if not coach:
        return cards.screenshot_needs_a_price(), None, None

    new_turns = len(deal.trajectory()) - before
    blocks = [cards.screenshot_started_deal(deal)] if seeded else []
    recap = cards.screenshot_recap(deal, new_turns, repeats=read.repeats,
                                   dropped=read.dropped)
    if recap:
        blocks.append(recap)
    blocks.append(coach)
    # Multi-turn reads earn the chart: the whole point is that the curve moved
    # more than once, and that is a picture, not a sentence.
    kind = "deal" if (new_turns > 1 or seeded) else None
    return "\n\n".join(blocks), kind, None


def _relay(deal: Deal, text: Optional[str], media: list[str]) -> tuple[str, Optional[str], None]:
    """One negotiation turn — the ~90% case (§4.1)."""
    if media:
        return _relay_screenshot(deal, text, media)

    # §7 A4: the listing 403'd, we asked for the asking price, this is it.
    if _awaiting_asking(deal) and _unblock_with_asking(deal, _asking_from_text(text)):
        return cards.unblocked(deal), "deal", None

    if deal.state is DealState.NEGOTIATING:
        coach = _process_seller_lines(deal, [text] if text else [])
        STORE.save_deal(deal)
        return (coach or cards.unparsed()), None, None
    if deal.state is DealState.AWAITING_LINK and not deal.listing_link:
        return cards.onboarding(), None, None
    return cards.not_negotiating(deal), None, None


_AFFIRM = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "do it",
           "confirm", "delete it", "go ahead", "kill it"}


def _affirmative(text: Optional[str]) -> bool:
    return (text or "").strip().strip(" \t\n.,!?…:;-–—\"'").lower() in _AFFIRM


def _dispatch(deal: Deal, text: Optional[str], media: list[str], meta: dict, *,
              research_bg: bool, parked: Optional[Deal]) -> tuple[str, Optional[str], Optional[list]]:
    """One branch per `Intent` (§7 A5). Returns (reply, card_kind, listed_ids).

    `card_kind` is what this reply teaches the *next* message — it gates the
    bare-integer SWITCH rule. `listed_ids` is the ordering a number resolves
    against, and is None when the reply changed neither.
    """
    user_id = deal.user_id
    Kind = intent.Intent

    # A held DELETE confirmation short-circuits the grammar: "yes" is a RELAY,
    # and it must not become one while we are holding a question open (§4.1
    # "confirm first"). Anything that is not a yes cancels and routes normally.
    pending = meta.pop("pending_delete", None)
    if pending and _affirmative(text):
        target = STORE.get_deal(pending)
        if target is not None and target.user_id == user_id:
            name = target.display_name()
            STORE.delete_deal(target.id)
            if STORE.get_focus(user_id) == target.id:
                left = STORE.list_deals(user_id)
                STORE.set_focus(user_id, left[0].id if left else "")
            return cards.deleted(name), None, None

    c = intent.classify(text, has_image=bool(media),
                        last_card_kind=meta.get("last_card_kind"),
                        awaiting_asking=_awaiting_asking(deal))

    if c.intent is Kind.NEW:
        url = c.url or _find_url(text)
        return _start_new_deal(deal, url, parked=parked, research_bg=research_bg,
                               description="" if url else c.meta.get("description", ""))

    if c.intent is Kind.HELP:
        return cards.help_card(), "help", None

    if c.intent is Kind.LIST:
        deals = _real_deals(user_id)
        if not deals:
            return cards.no_deals(), None, []
        return cards.deal_list(deals, STORE.get_focus(user_id)), "list", [d.id for d in deals]

    if c.intent is Kind.STATS:
        deals = _real_deals(user_id)
        return (cards.stats_card(deals) if deals else cards.no_deals()), "stats", None

    if c.intent is Kind.SWITCH:
        pool = _switch_pool(user_id, meta)
        if not c.arg:                                  # bare "/switch" — show the board
            if not pool:
                return cards.no_deals(), None, []
            return cards.deal_list(pool, STORE.get_focus(user_id)), "list", [d.id for d in pool]
        if c.why == "bare-index":
            # A number typed at a numbered list is an index, full stop. Running
            # it through the §4.1 name tiers first lets it match a *title* —
            # every "2019 Mazda CX-5" contains a 1, a 2, a 5 and a 9 — and the
            # cheapest context switch in the product turns into a disambiguation
            # prompt against two identical-looking rows.
            i = int(c.arg)
            target = pool[i - 1] if 1 <= i <= len(pool) else None
            candidates = []
        else:
            target, candidates = intent.resolve_switch(c.arg, pool)
        if target is not None:
            STORE.set_focus(user_id, target.id)
            return f"{cards.switched(target)}\n\n{cards.deal_card(target)}", "deal", None
        if candidates:
            return (cards.ambiguous_switch(c.arg, candidates), "list",
                    [d.id for d in candidates])
        return cards.no_match(c.arg), None, None

    if c.intent is Kind.CARD:
        return cards.deal_card(deal), "deal", None

    if c.intent is Kind.EXPLAIN:
        # §7 B5 — "why" and the ❓ tapback land on the same function.
        return cards.explain(deal), "explain", None

    if c.intent is Kind.CLOSE:
        if deal.state is not DealState.NEGOTIATING:
            return cards.not_negotiating(deal), None, None
        deal.state = DealState.CLOSED
        # Freeze the price now. The stats card sums it across every closed deal,
        # so it must not be re-derived later from a log UNDO could change.
        deal.closed_price = float(deal.last_user_offer or deal.last_seller_price or 0)
        msg = cards.closed_message(deal)
        deal.log_turn("closer", msg)
        STORE.save_deal(deal)
        return msg, None, None

    if c.intent is Kind.WALK:
        if deal.state is not DealState.NEGOTIATING:
            return cards.not_negotiating(deal), None, None
        deal.state = DealState.WALKED
        msg = cards.walked_message(deal)
        deal.log_turn("closer", msg)
        STORE.save_deal(deal)
        return msg, None, None

    if c.intent is Kind.UNDO:
        if not _undo(deal):
            return cards.nothing_to_undo(), None, None
        STORE.save_deal(deal)
        return cards.undone(deal), None, None

    if c.intent is Kind.RENAME:
        if not c.arg:
            return cards.help_card(), "help", None
        deal.nickname = c.arg
        STORE.save_deal(deal)
        return cards.renamed(deal), None, None

    if c.intent is Kind.DELETE:
        if not c.arg:
            return cards.help_card(), "help", None
        target, candidates = intent.resolve_switch(c.arg, _switch_pool(user_id, meta))
        if target is not None:
            meta["pending_delete"] = target.id
            return cards.confirm_delete(target), None, None
        if candidates:
            return (cards.ambiguous_switch(c.arg, candidates), "list",
                    [d.id for d in candidates])
        return cards.no_match(c.arg), None, None

    return _relay(deal, text, media)


def _outcome_effect(deal: Deal, before: DealState) -> Optional[str]:
    """§5.4 — the three effects, derived from the state transition this turn made.

    Read off the transition rather than plumbed out of `_dispatch` so every path
    that can close a deal gets it for free, and so a re-sent "we have a deal" on
    an already-closed deal does not fire confetti twice.

    `celebration` outranks `confetti` on a user's very first close: it happens
    once per account, and it is the moment the product proved itself.
    """
    if deal.state is DealState.CLOSED and before is not DealState.CLOSED:
        others = [d for d in STORE.list_deals(deal.user_id)
                  if d.id != deal.id and d.state is DealState.CLOSED]
        return "confetti" if others else "celebration"
    if deal.state is DealState.WALKED and before is not DealState.WALKED:
        return "slam"           # the physical thud sells the gravity
    return None


def _card_image(deal: Deal, kind: Optional[str]) -> Optional[tuple[bytes, str]]:
    """The PNG that belongs with this reply, or None (§5.5).

    Keyed off the `card_kind` the dispatcher already returns, so every path that
    produces a deal card — `card`, a SWITCH, the ❓ explanation — gets the chart
    without a second decision about when to attach one.

    Rendering is local (matplotlib, no network) and takes a few hundred ms, all
    of it inside the typing indicator. `PNG_CARDS=false` turns the whole thing
    off from `.env` without a deploy, which is the switch to reach for if the
    chart ever misbehaves in front of an audience.
    """
    if not PNG_CARDS or not kind:
        return None
    try:
        if kind == "deal":
            return render.deal_png(deal), "deal-card.png"
        if kind == "stats":
            return render.stats_png(_real_deals(deal.user_id)), "stats.png"
    except Exception:
        return None                    # the Unicode card is the deliverable
    return None


def route_message(deal: Deal, text: Optional[str], media: list[str], *,
                  send: bool, research_bg: bool = True,
                  parked: Optional[Deal] = None) -> str:
    """Advance a deal by one inbound message; return Closer's reply text.

    Contract unchanged for `/simulate`, the dashboard relay and the demo
    runbook — `parked` is additive and only the webhook sets it.
    """
    meta = STORE.get_user_meta(deal.user_id)
    before = deal.state
    reply, kind, listed = _dispatch(deal, text, media, meta,
                                    research_bg=research_bg, parked=parked)
    meta["last_card_kind"] = kind
    if listed is not None:
        meta["last_list"] = listed
    STORE.set_user_meta(deal.user_id, meta)

    if send and deal.phone and linq.available():
        effect = _outcome_effect(deal, before)
        _deliver(deal.phone, reply, effect=effect, image=_card_image(deal, kind))
    return reply


def _deliver(phone: str, reply: str, *, effect: Optional[str],
             image: Optional[tuple[bytes, str]]) -> None:
    """Put one reply in the thread, with whatever decoration it earned.

    The text is the deliverable and the image is an upgrade on top of it, so the
    fallback ladder is strict: try the attachment, and if the upload or the send
    fails for any reason, send the same text without it. §5.5 is explicit that
    the Unicode card ships first and the chart never blocks it — a CDN hiccup
    must not cost the user their number.
    """
    if image is not None:
        data, filename = image
        try:
            linq.send_media_bytes(phone, reply, data, filename, effect=effect)
            return
        except Exception:
            pass                       # fall through to the plain send
    try:
        if effect:
            # `send_effect` retries without the effect if the API rejects it, so
            # the close message lands even on the day `confetti` changes meaning.
            linq.send_effect(phone, reply, effect)
        else:
            linq.send(phone, reply)
    except Exception:
        pass


# ── who is this, and which of their deals are we talking about ───────────────
def _resolve_user(sender: Optional[str]) -> str:
    """The phone number is the account. Trust model lives in `state.user_id_for`."""
    return user_id_for(sender)


def _focused_deal(user_id: str, chat_id: Optional[str] = None) -> Optional[Deal]:
    """The deal an unqualified message applies to (§4.2 resolution order).

    Stored focus → most recently updated active deal → most recent deal of any
    state → None, which means this user has no deals yet and gets onboarding.
    An explicit SWITCH is resolved by the caller before this runs.

    `find_active_by_phone` is deliberately not consulted: focus is explicit and
    sticky, so a user who switched back to an older deal stays there even though
    a newer one is more recently touched.
    """
    focus_id = STORE.get_focus(user_id)
    if focus_id:
        deal = STORE.get_deal(focus_id)
        if deal:
            return deal
    deals = STORE.list_deals(user_id)          # already most-recent-first
    if not deals:
        return None
    return next((d for d in deals if d.is_active()), deals[0])


def _adopt(deal: Deal, chat_id: Optional[str], phone: Optional[str]) -> Deal:
    """Backfill routing identifiers we only learn from an inbound message."""
    changed = False
    if chat_id and not deal.chat_id:
        deal.chat_id, changed = chat_id, True
    if phone and not deal.phone:
        deal.phone, changed = phone, True
    if changed:
        STORE.save_deal(deal)
    return deal


def _new_deal(user_id: str, chat_id: Optional[str], phone: Optional[str]) -> Deal:
    deal = Deal(user_id=user_id, phone=phone, chat_id=chat_id)
    STORE.save_deal(deal)
    STORE.set_focus(user_id, deal.id)
    return deal


def _inbound_deal(user_id: str, chat_id: Optional[str], phone: Optional[str],
                  text: Optional[str], *,
                  has_image: bool = False) -> tuple[Deal, Optional[Deal]]:
    """Resolve the deal an inbound message belongs to. Returns (deal, parked).

    A listing link ALWAYS starts a new deal and takes focus — a link is never
    folded into an existing negotiation. The one exception is the empty shell
    created for a brand-new user, which has nothing to preserve and would
    otherwise be orphaned by its own first message.

    A car described in words does the same thing, and has to be decided here as
    well as in `_dispatch`: this function picks which deal the message lands on,
    so if it disagrees with the router the description starts a deal that the
    router then researches onto the *previous* one. `_starts_a_deal` is the one
    predicate both sides ask.
    """
    focused = _focused_deal(user_id, chat_id)
    starts = _starts_a_deal(text, has_image=has_image)

    if starts and focused is not None and focused.listing_link is None \
            and focused.listing_desc is None \
            and focused.state == DealState.AWAITING_LINK:
        return _adopt(focused, chat_id, phone), None      # onboarding shell

    if starts and focused is not None:
        parked = focused if focused.is_active() else None
        return _new_deal(user_id, chat_id, phone), parked

    if focused is None:
        return _new_deal(user_id, chat_id, phone), None

    return _adopt(focused, chat_id, phone), None


def _send_now(phone: Optional[str], msg: str) -> None:
    if phone and linq.available():
        try:
            linq.send(phone, msg)
        except Exception:
            pass


# §5.2 — how far a 👎 moves the number. A quarter of the gap between our offer
# and what they are asking is one visible notch: enough that the user sees a
# different number, small enough that three taps don't hand over the whole
# negotiation.
SOFTER_NOTCH = 0.25


def _softer(deal: Deal) -> Optional[tuple[float, Optional[float]]]:
    """One notch softer than the standing recommendation, priced off the posterior.

    Returns `(offer, p_accept)` or None when there is nothing to soften. The
    probability is recomputed rather than reused: a softer offer has genuinely
    better odds and quoting the old ones would be the one lie this product
    cannot afford.
    """
    snap = deal.snapshot or {}
    offer = snap.get("offer")
    if offer is None:
        return None
    target = deal.last_seller_price or deal.asking
    if not target or target <= offer:
        return None
    nudged = float(offer) + SOFTER_NOTCH * (float(target) - float(offer))
    belief = deal.belief()
    return round(nudged, 2), (belief.p_accept(nudged) if belief else None)


def _process_reaction(rx: linq.InboundReaction) -> None:
    """A tapback on one of our messages, treated as a command (§5.2).

    Resolved against the user's focused deal rather than against the specific
    message the tapback landed on. In this medium those are the same thing
    ~always — the tapback is a reply to what we just said — and focus is already
    the resolution rule every unqualified message uses (§4.2), so the two agree
    by construction instead of by a second lookup table that could disagree.
    """
    user_id = _resolve_user(rx.sender)
    phone = rx.sender
    try:
        deal = _focused_deal(user_id)
        if deal is None:
            return
        kind = rx.reaction

        if kind == "question":                      # ❓ explain the math
            # The chart is the answer to "why" more than the prose is — the
            # flat stretch in the curve IS the argument — so the explanation
            # carries the same PNG the `card` command would.
            _deliver(phone, cards.explain(deal), effect=None,
                     image=_card_image(deal, "deal"))
            return
        if kind == "like":                          # 👍 "sent it"
            _send_now(phone, cards.offer_locked(deal))
            return
        if kind == "emphasize":                     # ‼️ pin this deal
            STORE.set_focus(user_id, deal.id)
            _send_now(phone, cards.pinned(deal))
            return
        if kind == "dislike":                       # 👎 a different number
            softer = _softer(deal)
            if softer is None:
                _send_now(phone, cards.unparsed())
                return
            offer, p = softer
            deal.last_user_offer = offer
            if deal.snapshot:
                deal.snapshot = {**deal.snapshot, "offer": offer, "p_accept": p}
            msg = cards.softer_offer(deal, offer, p)
            deal.log_turn("closer", msg)
            STORE.save_deal(deal)
            _send_now(phone, msg)
    except Exception:
        # Runs on a worker thread — an escaping exception is a silent no-op the
        # user reads as the tapback not working. Say something instead.
        _send_now(phone, cards.error())


def _signal_reaction(inb: linq.InboundMessage, deal: Deal) -> None:
    """The tapback that says what we *thought*, once the turn resolved.

    The only tapbacks we send on an inbound message are the meaning-carrying
    ones: ❗ for a bluff we just caught, ❤️ for the message that closed the deal.
    There is deliberately no blanket 👍 read receipt — "we got it" is already
    carried by the typing indicator, and a tapback on every message would make
    these two invisible.

    Silent by construction — `react` swallows its own failures.
    """
    if not inb.message_id:
        return
    if deal.state is DealState.CLOSED:
        linq.react(inb.message_id, "love")
        return
    last = (deal.signals_log or [])[-1:]
    if last and last[0].get("bluff_claim"):
        linq.react(inb.message_id, "emphasize")


def _rate_check(user_id: str, now: Optional[float] = None) -> tuple[bool, bool]:
    """§3: 20 inbound messages per phone per minute. Returns (allowed, notify).

    The reply itself is rate-limited too — a throttled user who keeps typing
    gets one polite line per window, not twenty.
    """
    now = now if now is not None else time.time()
    meta = STORE.get_user_meta(user_id)
    times = [t for t in (meta.get("msg_times") or []) if now - t < RATE_WINDOW]
    times.append(now)
    meta["msg_times"] = times[-(MAX_INBOUND_PER_MINUTE * 2):]
    over = len(times) > MAX_INBOUND_PER_MINUTE
    notify = over and (now - float(meta.get("throttled_at") or 0.0)) >= RATE_WINDOW
    if notify:
        meta["throttled_at"] = now
    STORE.set_user_meta(user_id, meta)
    return (not over), notify


def _at_deal_limit(user_id: str) -> bool:
    """§3: 10 running deals per phone. Closed and walked deals don't count —
    they are the stats card's data, not load."""
    return sum(1 for d in STORE.list_deals(user_id) if d.is_active()) >= MAX_ACTIVE_DEALS


def _process_inbound(inb: linq.InboundMessage) -> str:
    user_id = _resolve_user(inb.sender)
    phone = inb.sender
    try:
        # No blanket read-receipt tapback. The typing indicator below already
        # says "we have your message" for the whole turn, and a 👍 on literally
        # every inbound is noise that drowns the two tapbacks that carry meaning
        # (`_signal_reaction`: ❗ bluff, ❤️ closed).
        allowed, notify = _rate_check(user_id)
        if not allowed:
            msg = cards.throttled()
            if notify:
                _send_now(phone, msg)
            return msg

        has_image = bool(inb.media_urls)
        if _starts_a_deal(inb.text, has_image=has_image) and _at_deal_limit(user_id):
            msg = cards.deal_limit(MAX_ACTIVE_DEALS)
            _send_now(phone, msg)
            return msg

        deal, parked = _inbound_deal(user_id, inb.chat_id, phone, inb.text,
                                     has_image=has_image)
        # §5.3 — hold a typing indicator for the whole turn. `typing_while`
        # clears it in a `finally`, so an exception below cannot leave the thread
        # showing us typing forever.
        with linq.typing_while(inb.chat_id or deal.chat_id):
            reply = route_message(deal, inb.text, inb.media_urls,
                                  send=True, research_bg=True, parked=parked)
        _signal_reaction(inb, deal)
        return reply
    except Exception:
        # This runs on a worker thread: an escaping exception is a text that
        # silently never arrives. Never apologise, never explain the stack.
        msg = cards.error()
        _send_now(phone, msg)
        return msg


# ── routes: webhook ──────────────────────────────────────────────────────────
@app.post("/webhooks/linq")
async def webhook(request: Request,
                  x_webhook_signature: Optional[str] = Header(default=None)):
    raw = await request.body()
    if not linq.verify_signature(raw, x_webhook_signature):
        raise HTTPException(status_code=401, detail="bad signature")
    # Stamp before parsing: a typing indicator or a delivery receipt is not a
    # message, but it IS proof the listener is alive, which is what /health/inbound
    # answers.
    _INBOUND["events"] += 1
    _INBOUND["last_event_ts"] = time.time()
    try:
        body = await request.json()
    except Exception:
        _INBOUND["ignored"] += 1
        return {"ok": True, "ignored": "no json"}
    # §5.2 — a tapback on one of our messages is a first-class command. Checked
    # before `parse_webhook` because reaction events are a different shape
    # entirely; `parse_reaction` drops our own echoes (`is_from_me`), without
    # which every 👍 we send in §5.1 would re-enter as user input.
    rx = linq.parse_reaction(body)
    if rx is not None:
        if rx.removed or not rx.reaction:
            _INBOUND["ignored"] += 1
            return {"ok": True, "ignored": "reaction"}
        _INBOUND["reactions"] += 1
        asyncio.create_task(asyncio.to_thread(_process_reaction, rx))
        return {"ok": True}

    inb = linq.parse_webhook(body)
    if not inb or not inb.has_content():
        _INBOUND["ignored"] += 1
        return {"ok": True, "ignored": True}
    _INBOUND["messages"] += 1
    _INBOUND["last_message_ts"] = _INBOUND["last_event_ts"]
    _INBOUND["last_sender"] = inb.sender
    # Return 200 fast; do the (blocking) LLM/research work off the event loop.
    asyncio.create_task(asyncio.to_thread(_process_inbound, inb))
    return {"ok": True}


# ── routes: dashboard API (Clerk-authed) ─────────────────────────────────────
class CreateDeal(BaseModel):
    listing_link: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    asking: Optional[float] = None


class RelayMessage(BaseModel):
    text: Optional[str] = None
    image_url: Optional[str] = None


class LinkBody(BaseModel):
    listing_link: str


def _owned(deal_id: str, user_id: str) -> Deal:
    deal = STORE.get_deal(deal_id)
    if not deal or deal.user_id != user_id:
        raise HTTPException(status_code=404, detail="deal not found")
    return deal


@app.post("/api/deals")
async def create_deal(body: CreateDeal, user_id: str = Depends(require_user)):
    deal = Deal(user_id=user_id, phone=body.phone, asking=body.asking,
                title=body.title or "New deal")
    STORE.save_deal(deal)
    if body.listing_link:
        _start_research(deal, body.listing_link, background=True)
    return deal.public()


@app.get("/api/deals")
async def list_deals(user_id: str = Depends(require_user)):
    return {"deals": [d.public() for d in STORE.list_deals(user_id)]}


@app.get("/api/deals/{deal_id}")
async def get_deal(deal_id: str, user_id: str = Depends(require_user)):
    return _owned(deal_id, user_id).public()


@app.delete("/api/deals/{deal_id}")
async def delete_deal(deal_id: str, user_id: str = Depends(require_user)):
    _owned(deal_id, user_id)
    STORE.delete_deal(deal_id)
    return {"ok": True}


@app.post("/api/deals/{deal_id}/link")
async def set_link(deal_id: str, body: LinkBody, user_id: str = Depends(require_user)):
    deal = _owned(deal_id, user_id)
    _start_research(deal, body.listing_link, background=True)
    return STORE.get_deal(deal_id).public()


@app.post("/api/deals/{deal_id}/messages")
async def relay_message(deal_id: str, body: RelayMessage,
                        user_id: str = Depends(require_user)):
    deal = _owned(deal_id, user_id)
    media = [body.image_url] if body.image_url else []

    def run() -> str:
        return route_message(deal, body.text, media, send=False, research_bg=True)

    reply = await asyncio.to_thread(run)
    fresh = STORE.get_deal(deal_id)
    return {"message": reply, "deal": fresh.public() if fresh else None}


# ── routes: simulate (keyboard demo, no auth, no phone) ──────────────────────
class Simulate(BaseModel):
    text: str = ""
    deal_id: Optional[str] = None
    phone: Optional[str] = None
    # Screenshots, so the §7 A1 path is testable without a phone in the loop.
    # Each entry is an https URL, a data URI, or raw base64 — `app.runware`
    # inlines all three.
    images: list[str] = []
    image_url: Optional[str] = None                # convenience for a single one


@app.post("/simulate")
async def simulate(body: Simulate):
    if body.deal_id:
        deal = STORE.get_deal(body.deal_id)
        if not deal:
            raise HTTPException(status_code=404, detail="deal not found")
    else:
        deal = Deal(user_id=DEV_USER_ID, phone=body.phone, title="Demo deal")
        STORE.save_deal(deal)

    media = list(body.images) + ([body.image_url] if body.image_url else [])

    def run() -> str:
        # inline research so a scripted curl demo sees the final state synchronously
        return route_message(deal, body.text or None, media,
                             send=False, research_bg=False)

    reply = await asyncio.to_thread(run)
    # A link starts a NEW deal and moves focus, so report the deal the user is
    # actually on — otherwise a scripted rehearsal silently keeps polling the
    # one it just parked.
    focus_id = STORE.get_focus(deal.user_id) or deal.id
    fresh = STORE.get_deal(focus_id) or STORE.get_deal(deal.id)
    return {"deal_id": fresh.id if fresh else deal.id, "message": reply,
            "state": fresh.state.value if fresh else None,
            "snapshot": fresh.snapshot if fresh else None}


# ── routes: dashboard state + static ─────────────────────────────────────────
@app.get("/state")
async def state(deal_id: Optional[str] = None, user_id: Optional[str] = None):
    if deal_id:
        deal = STORE.get_deal(deal_id)
    else:
        pool = STORE.list_deals(user_id or DEV_USER_ID)
        deal = pool[0] if pool else None
    if not deal:
        return {"deal": None}
    return {"deal": deal.public()}


@app.get("/health")
async def health():
    return {
        "ok": True,
        "store": store_mod.backend_name(),
        "runware": runware.available(),
        "linq": linq.available(),
        "clerk": clerk_enabled(),
        "research_mode": research.RESEARCH_MODE,
    }


@app.get("/health/inbound")
async def health_inbound():
    """Is the number still answering?

    `linq webhooks listen` dying is a silent outage — texts vanish with no
    error anywhere. `stale` is the alarm: nothing at all has arrived (event or
    message) since `INBOUND_STALE_SECONDS` ago, which means restart the
    listener. Age is measured from boot until the first event, so a freshly
    started process is not instantly stale.
    """
    now = time.time()
    since = _INBOUND["last_event_ts"] or _INBOUND["started_at"]
    age = now - since
    return {
        "ok": True,
        "stale": age > INBOUND_STALE_SECONDS,
        "stale_after_seconds": INBOUND_STALE_SECONDS,
        "seconds_since_last_event": round(age, 1),
        "events": _INBOUND["events"],
        "messages": _INBOUND["messages"],
        "ignored": _INBOUND["ignored"],
        "last_event_ts": _INBOUND["last_event_ts"],
        "last_message_ts": _INBOUND["last_message_ts"],
        "last_sender": _INBOUND["last_sender"],
        "uptime_seconds": round(now - _INBOUND["started_at"], 1),
        "listener": ("linq webhooks listen --profile closer "
                     "--forward-to http://localhost:8000/webhooks/linq"),
    }


@app.post("/tasks/run-research")
async def run_pending_research(x_cron_secret: Optional[str] = Header(default=None),
                               authorization: Optional[str] = Header(default=None)):
    """Serverless fallback: drain AWAITING_RESEARCH deals whose background thread
    didn't run (e.g. a frozen Vercel function). Idempotent; only picks up stale deals.
    Auth accepts `X-Cron-Secret: <s>` or Vercel Cron's `Authorization: Bearer <s>`."""
    if CRON_SECRET:
        bearer = (authorization or "").removeprefix("Bearer ").strip()
        if x_cron_secret != CRON_SECRET and bearer != CRON_SECRET:
            raise HTTPException(status_code=401, detail="bad cron secret")
    picked = []
    for deal in STORE.list_pending_research():
        if time.time() - deal.updated_at > 45 and deal.listing_link:
            picked.append(deal.id)
            await asyncio.to_thread(_do_research, deal.id, deal.listing_link)
    return {"ran": picked}


@app.on_event("startup")
async def _seed_on_startup():
    if DEMO_MODE:
        try:
            demo.seed_demo()
        except Exception:
            pass


@app.post("/demo/seed")
async def demo_seed():
    d = demo.seed_demo()
    return {"deal_id": d.id, "state": d.state.value, "open": f"/?deal={d.id}"}


@app.get("/", response_class=HTMLResponse)
async def index():
    f = STATIC_DIR / "dashboard.html"
    if f.exists():
        return FileResponse(f)
    return HTMLResponse("<h1>Closer API</h1><p>Dashboard not bundled. "
                        "See <a href='/health'>/health</a>.</p>")
