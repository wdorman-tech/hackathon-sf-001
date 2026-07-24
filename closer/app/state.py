"""Closer — negotiation state model (Phase 3).

A Clerk user owns many Deals. A Deal is one car negotiation and moves through:

    AWAITING_LINK -> AWAITING_RESEARCH -> NEGOTIATING -> CLOSED | WALKED

The Deal is the persisted unit (see app.store). We do NOT serialize the numpy
BeliefState — we persist the ordered `signals_log` (the source of truth) and a
`snapshot` (latest belief curve + recommendation) for fast dashboard reads. The
live BeliefState is reconstructed on demand by replaying the log, which keeps the
store engine-agnostic (a teammate's tuned engine drops in with no migration).
"""

from __future__ import annotations

import re
import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.engine import BeliefState, Signals

# Which price caps our offers and gates the WALK rule. The engine defaults to
# "R" (the walk-away target), which is spec-literal but walks on turn one of a
# real listing: the seller's opening anchor sits far above an aggressive R, so
# P(floor <= R) is under the walk threshold before we have countered even once.
# "V" lets offers run to expert fair value, which is the behaviour the coach
# flow is built around — counter, converge, then hold. Decision-layer only; the
# posterior over the seller's floor is identical either way.
OFFER_CEILING = "V"


def normalize_e164(handle: Optional[str]) -> Optional[str]:
    """Best-effort E.164 for a Linq sender handle.

    Linq usually delivers `+12055551234`, but handles also arrive as
    `12055551234`, `(205) 555-1234`, or padded with whitespace. Normalizing on
    every read is what stops one phone becoming two users — and therefore two
    disjoint sets of deals. iMessage Apple-ID handles are emails, not numbers;
    those pass through lowercased rather than being mangled into digits.
    """
    if not handle:
        return None
    raw = handle.strip()
    if not raw:
        return None
    if "@" in raw:                                   # Apple ID / email handle
        return raw.removeprefix("mailto:").lower()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:                            # bare US number
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def user_id_for(handle: Optional[str]) -> str:
    """`user_id = "phone:" + normalize_e164(sender_handle)` — the whole auth system.

    Linq's webhook carries `data.sender_handle.handle`, the E.164 number Apple
    resolved for the sender. It is not user-supplied: it comes from the carrier
    /Apple side of the connection. So there is no signup, no login, no session,
    and isolation is automatic — a different phone is a different `user_id` and
    no code path reads across them.

    Trust model, deliberately chosen: we trust Linq's sender handle. A SIM swap
    or a spoofed handle would impersonate a user. For a negotiation coach whose
    worst case is someone seeing another person's car deal, that is the right
    trade for this event.
    """
    normalized = normalize_e164(handle)
    return f"phone:{normalized}" if normalized else "phone:unknown"


class DealState(str, Enum):
    AWAITING_LINK = "AWAITING_LINK"
    AWAITING_RESEARCH = "AWAITING_RESEARCH"
    NEGOTIATING = "NEGOTIATING"
    CLOSED = "CLOSED"
    WALKED = "WALKED"


class TurnRecord(BaseModel):
    role: str                                  # seller | closer | system | user
    text: str
    ts: float = Field(default_factory=time.time)
    signals: Optional[dict] = None             # engine Signals for a seller turn
    recommendation: Optional[dict] = None       # engine recommend() for a closer turn


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Deal(BaseModel):
    id: str = Field(default_factory=_new_id)
    user_id: str
    chat_id: Optional[str] = None              # Linq chat id (webhook routing)
    phone: Optional[str] = None                # the user's phone (relay source)
    title: str = "New deal"
    nickname: Optional[str] = None             # user-assigned; wins over `title` in cards

    listing_link: Optional[str] = None
    # The car in the buyer's own words, when they had no link to send. Research
    # values either (`research.run_research`), so a deal is "real" if it has one
    # of the two — see `main._real_deals`.
    listing_desc: Optional[str] = None
    state: DealState = DealState.AWAITING_LINK

    # Valuation truth — Closer's own agentic research (app.research), with sources.
    research: Optional[dict] = None
    asking: Optional[float] = None
    R: Optional[float] = None                   # walk-away target
    V: Optional[float] = None                   # fair value
    research_steps: list[dict] = Field(default_factory=list)   # live tool trace

    # Negotiation history.
    signals_log: list[dict] = Field(default_factory=list)
    last_seller_price: Optional[float] = None
    last_user_offer: Optional[float] = None
    feed: list[TurnRecord] = Field(default_factory=list)
    snapshot: Optional[dict] = None             # latest recommendation + floor_map

    # Fingerprints of seller lines already replayed off a screenshot
    # (`app.screenshot.fingerprint`). Two screenshots of one thread overlap in
    # the middle — this is what stops the shared bubbles updating the posterior
    # twice on evidence that only happened once.
    seen_screenshot_lines: list[str] = Field(default_factory=list)

    # Frozen at the moment of close. The stats card sums this across every closed
    # deal, so it cannot be re-derived later from a log that UNDO may have changed.
    closed_price: Optional[float] = None

    created_at: float = Field(default_factory=_now)
    updated_at: float = Field(default_factory=_now)

    # ── helpers ──────────────────────────────────────────────────────────────
    def touch(self) -> None:
        self.updated_at = _now()

    def log_turn(self, role: str, text: str, *, signals: Optional[dict] = None,
                 recommendation: Optional[dict] = None) -> None:
        self.feed.append(TurnRecord(role=role, text=text, signals=signals,
                                    recommendation=recommendation))

    def belief(self) -> Optional[BeliefState]:
        """Reconstruct the live posterior by replaying the signal log.

        None — never an exception — when the deal has no numbers to build one
        from. A `blocked` research payload (§7 A4: the listing 403'd) sets
        asking/V/R to 0.0 rather than None, and `BeliefState` rejects a
        non-positive asking price. Every caller already handles None; letting
        that ValueError escape instead turned an answerable state into a
        stack trace on a worker thread, which the user reads as silence.
        """
        if self.asking is None or self.R is None or self.V is None:
            return None
        try:
            b = BeliefState(self.asking, self.R, self.V, offer_ceiling=OFFER_CEILING)
            for s in self.signals_log:
                b.update(Signals(**s))
        except (ValueError, TypeError):
            return None
        return b

    def display_name(self) -> str:
        """What the cards call this deal. A user-set nickname always wins."""
        return self.nickname or self.title

    def trajectory(self) -> list[dict]:
        """Per-turn belief history for the deal card.

        Pure derivation over `feed` — every closer turn already carries the full
        `recommend()` dict, so this needs no new persistence, works on deals
        created before it existed, and survives UNDO for free (UNDO truncates
        the feed). `signals` and `seller_text` are read off the preceding turn:
        the seller message that produced this recommendation.

        `seller_text` is what the deal card quotes in its bluff callout — the
        seller's own words on the turn the posterior refused to move. Without
        it the card can only say "the pressure play", which is a template, and
        the one line judges remember is the quote.
        """
        out: list[dict] = []
        for i, turn in enumerate(self.feed):
            if not turn.recommendation:
                continue
            prev = self.feed[i - 1] if i else None
            out.append({
                "turn": len(out) + 1,
                "ts": turn.ts,
                "floor_est": turn.recommendation.get("floor_point_est"),
                "floor_std": turn.recommendation.get("floor_std"),
                "seller_price": turn.recommendation.get("last_seller_price"),
                "our_offer": turn.recommendation.get("offer"),
                "p_accept": turn.recommendation.get("p_accept"),
                "action": turn.recommendation.get("action"),
                "signals": (prev.signals if prev else None),
                "seller_text": (prev.text if prev else None),
            })
        return out

    def is_active(self) -> bool:
        return self.state in (DealState.AWAITING_LINK, DealState.AWAITING_RESEARCH,
                              DealState.NEGOTIATING)

    def public(self) -> dict:
        """Shape the dashboard consumes (belief curve lives under `snapshot`)."""
        return {
            "id": self.id,
            "title": self.title,
            "nickname": self.nickname,
            "state": self.state.value,
            "listing_link": self.listing_link,
            "listing_desc": self.listing_desc,
            "phone": self.phone,
            "asking": self.asking,
            "R": self.R,
            "V": self.V,
            "research": self.research,
            "research_steps": self.research_steps,
            "last_seller_price": self.last_seller_price,
            "last_user_offer": self.last_user_offer,
            "closed_price": self.closed_price,
            "snapshot": self.snapshot,
            "trajectory": self.trajectory(),
            "feed": [t.model_dump() for t in self.feed],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
