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

import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.engine import BeliefState, Signals


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

    listing_link: Optional[str] = None
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
        """Reconstruct the live posterior by replaying the signal log."""
        if self.asking is None or self.R is None or self.V is None:
            return None
        b = BeliefState(self.asking, self.R, self.V)
        for s in self.signals_log:
            b.update(Signals(**s))
        return b

    def is_active(self) -> bool:
        return self.state in (DealState.AWAITING_LINK, DealState.AWAITING_RESEARCH,
                              DealState.NEGOTIATING)

    def public(self) -> dict:
        """Shape the dashboard consumes (belief curve lives under `snapshot`)."""
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state.value,
            "listing_link": self.listing_link,
            "phone": self.phone,
            "asking": self.asking,
            "R": self.R,
            "V": self.V,
            "research": self.research,
            "research_steps": self.research_steps,
            "last_seller_price": self.last_seller_price,
            "last_user_offer": self.last_user_offer,
            "snapshot": self.snapshot,
            "feed": [t.model_dump() for t in self.feed],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
