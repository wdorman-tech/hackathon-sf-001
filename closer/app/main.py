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

from app import demo, linq, llm, research, runware  # noqa: E402
from app import store as store_mod  # noqa: E402
from app.auth import DEV_USER_ID, clerk_enabled, require_user  # noqa: E402
from app.state import Deal, DealState  # noqa: E402

STORE = store_mod.get_store()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]

URL_RE = re.compile(r"https?://\S+")
CLOSE_KW = ("deal", "we have a deal", "done deal", "sold", "i'll take it", "i will take it",
            "took it", "bought it", "picked it up", "we agreed", "closing at", "closed at",
            "it's a deal", "its a deal")
WALK_KW = ("walked", "i walked", "i passed", "passed on it", "walk away", "walked away",
           "no deal", "moving on", "found another", "backed out")

app = FastAPI(title="Closer API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ── small helpers ────────────────────────────────────────────────────────────
def _find_url(text: Optional[str]) -> Optional[str]:
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


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
    return {**rec, "asking": deal.asking, "R": deal.R, "V": deal.V,
            "last_seller_price": deal.last_seller_price,
            "last_user_offer": deal.last_user_offer, "coach_message": coach}


def _detect_outcome(text: Optional[str], asking: float) -> Optional[str]:
    """A short confirmation ('deal' / 'i walked') with no NEW price = deal outcome.
    A message that quotes a price is a relayed seller offer → classify it instead."""
    if not text:
        return None
    if llm.extract_price(text, asking) is not None:
        return None
    low = text.lower()
    if any(k in low for k in WALK_KW):
        return "walked"
    if any(k in low for k in CLOSE_KW):
        return "closed"
    return None


# ── research kickoff (background thread on a long-running host; the /tasks cron
#    is the serverless fallback) ───────────────────────────────────────────────
def _do_research(deal_id: str, link: str) -> None:
    deal = STORE.get_deal(deal_id)
    if not deal or deal.state != DealState.AWAITING_RESEARCH:
        return

    def on_step(step: dict) -> None:
        d = STORE.get_deal(deal_id)
        if d and d.state == DealState.AWAITING_RESEARCH:
            d.research_steps.append(step)
            STORE.save_deal(d)

    payload = research.run_research(link, asking=deal.asking, on_step=on_step)
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


def _start_research(deal: Deal, link: str, *, background: bool) -> None:
    deal.listing_link = link
    deal.state = DealState.AWAITING_RESEARCH
    deal.research_steps = []
    STORE.save_deal(deal)
    if background:
        threading.Thread(target=_do_research, args=(deal.id, link), daemon=True).start()
    else:
        _do_research(deal.id, link)


# ── one negotiation turn (seller message → coach message) ────────────────────
def _process_seller_turn(deal: Deal, seller_text: Optional[str],
                         image_ref: Optional[str]) -> Optional[str]:
    asking = deal.asking or 16000.0

    if image_ref and not seller_text:
        try:
            ex = llm.extract_from_screenshot(image_ref)
            msgs = ex.get("seller_messages") or []
            seller_text = " ".join(msgs[-2:]).strip() or None
            if not seller_text and ex.get("latest_seller_price"):
                seller_text = f"They said {int(ex['latest_seller_price'])}."
        except Exception:
            seller_text = None
    if not seller_text:
        return None

    sig = llm.classify_seller_message(seller_text, deal.last_seller_price, asking)
    deal.signals_log.append(sig.as_dict())
    if sig.seller_price is not None:
        deal.last_seller_price = sig.seller_price

    belief = deal.belief()
    if belief is None:
        return None
    rec = belief.recommend(last_user_offer=_opening_offer(deal),
                           last_seller_price=deal.last_seller_price)
    coach = llm.draft_coach_message(
        rec, sig, _expert_for_draft(deal),
        {"last_seller_price": deal.last_seller_price, "last_user_offer": deal.last_user_offer})

    if rec["action"] == "COUNTER":
        deal.last_user_offer = rec["offer"]        # thread the user's next offer forward

    deal.log_turn("seller", seller_text, signals=sig.as_dict())
    deal.log_turn("closer", coach, recommendation=rec)
    deal.snapshot = _snapshot(deal, rec, coach)
    return coach


# ── the router (shared by webhook / simulate) ────────────────────────────────
def route_message(deal: Deal, text: Optional[str], media: list[str], *,
                  send: bool, research_bg: bool = True) -> str:
    """Advance a deal by one inbound message; return Closer's reply text."""
    to = deal.phone

    def out(msg: str, log: bool = True) -> str:
        if log:
            deal.log_turn("closer", msg)
        if send and to and linq.available():
            try:
                linq.send(to, msg)
            except Exception:
                pass
        return msg

    if deal.state == DealState.AWAITING_LINK:
        url = _find_url(text)
        if url:
            _start_research(deal, url, background=research_bg)
            return out("On it — researching this car and the comps now. Give me ~30s. 🔎")
        STORE.save_deal(deal)
        return out("Send me the used-car listing link and I'll research it, then coach every "
                   "counter so you don't overpay.")

    if deal.state == DealState.AWAITING_RESEARCH:
        return out("Still digging into comps — one sec.", log=False)

    if deal.state == DealState.NEGOTIATING:
        outcome = _detect_outcome(text, deal.asking or 16000.0)
        if outcome == "closed":
            price = deal.last_user_offer or deal.last_seller_price or 0
            deal.state = DealState.CLOSED
            STORE.save_deal(deal)
            under = int((deal.asking or 0) - price)
            tail = f" — ${under:,} under ask" if under > 0 else ""
            return out(f"🤝 Closed at ${int(price):,}{tail}. Great work.")
        if outcome == "walked":
            deal.state = DealState.WALKED
            STORE.save_deal(deal)
            return out("Smart — better than overpaying. Logged as walked. "
                       "Text a new listing link whenever you want to run another.")
        coach = _process_seller_turn(deal, text, media[0] if media else None)
        STORE.save_deal(deal)
        if coach is None:
            return out("Didn't catch a seller message — paste their text, or a screenshot "
                       "of your chat with them.")
        return out(coach, log=False)   # _process_seller_turn already logged the closer turn

    # CLOSED / WALKED
    url = _find_url(text)
    if url:
        deal.signals_log, deal.feed, deal.snapshot = [], [], None
        deal.last_seller_price = deal.last_user_offer = None
        _start_research(deal, url, background=research_bg)
        return out("New one? On it — researching now. 🔎")
    return out("This deal's wrapped. Send a new listing link to start another.")


def _resolve_or_create(chat_id: Optional[str], sender: Optional[str]) -> Deal:
    deal = STORE.find_by_chat(chat_id) if chat_id else None
    if not deal and sender:
        deal = STORE.find_active_by_phone(sender)
    if not deal:
        deal = Deal(user_id=f"phone:{sender or 'unknown'}", phone=sender, chat_id=chat_id)
        STORE.save_deal(deal)
        return deal
    changed = False
    if chat_id and not deal.chat_id:
        deal.chat_id, changed = chat_id, True
    if sender and not deal.phone:
        deal.phone, changed = sender, True
    if changed:
        STORE.save_deal(deal)
    return deal


def _process_inbound(inb: linq.InboundMessage) -> None:
    deal = _resolve_or_create(inb.chat_id, inb.sender)
    route_message(deal, inb.text, inb.media_urls, send=True, research_bg=True)


# ── routes: webhook ──────────────────────────────────────────────────────────
@app.post("/webhooks/linq")
async def webhook(request: Request,
                  x_webhook_signature: Optional[str] = Header(default=None)):
    raw = await request.body()
    if not linq.verify_signature(raw, x_webhook_signature):
        raise HTTPException(status_code=401, detail="bad signature")
    try:
        body = await request.json()
    except Exception:
        return {"ok": True, "ignored": "no json"}
    inb = linq.parse_webhook(body)
    if not inb or not inb.has_content():
        return {"ok": True, "ignored": True}
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
    text: str
    deal_id: Optional[str] = None
    phone: Optional[str] = None


@app.post("/simulate")
async def simulate(body: Simulate):
    if body.deal_id:
        deal = STORE.get_deal(body.deal_id)
        if not deal:
            raise HTTPException(status_code=404, detail="deal not found")
    else:
        deal = Deal(user_id=DEV_USER_ID, phone=body.phone, title="Demo deal")
        STORE.save_deal(deal)

    def run() -> str:
        # inline research so a scripted curl demo sees the final state synchronously
        return route_message(deal, body.text, [], send=False, research_bg=False)

    reply = await asyncio.to_thread(run)
    fresh = STORE.get_deal(deal.id)
    return {"deal_id": deal.id, "message": reply,
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


@app.post("/tasks/run-research")
async def run_pending_research(x_cron_secret: Optional[str] = Header(default=None)):
    """Serverless fallback: drain AWAITING_RESEARCH deals whose background thread
    didn't run (e.g. a frozen Vercel function). Idempotent; only picks up stale deals."""
    if CRON_SECRET and x_cron_secret != CRON_SECRET:
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
