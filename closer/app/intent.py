"""Intent router — the command grammar from update_1.md §4.1.

STUB. Lane B (`lane/agent`) owns this file and fills in `classify`. It is
committed to main ahead of the lanes so Lane A (`main.py`) and Lane D (demo
scripts) can import the frozen names without waiting on the implementation.

The seam is the enum and `classify`'s signature. Both are frozen; the body is
not. Nothing in the repo imports this yet, so a partial implementation here
cannot regress the live path.

━━ The hard rule ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    If a message contains a price, it is a seller relay. Never a command.

~90% of real traffic is "he said 5400". Misrouting a relay into a command
breaks a live negotiation, so RELAY is the default for everything unmatched.
`main.py:109 _detect_outcome` already applies this exact test for close/walk —
extend it, do not reinvent it.

Rules only, LLM never: intent classification must not add a Runware round-trip
to every seller message. A leading `/` forces command interpretation and is the
escape hatch for genuinely ambiguous input.

━━ Trigger table (§4.1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    RELAY   default — anything unmatched, anything with a price, any image
    NEW     a URL anywhere in the message
    LIST    deals · my deals · list · /deals · what am I working on
    SWITCH  switch to X · go to X · X deal · bare int 1-10 · /switch X
    CARD    card · status · where are we · show me · the curve · /card
    STATS   stats · how much have I saved · savings · total · /stats
    CLOSE   CLOSE_KW (main.py:50)
    WALK    WALK_KW (main.py:52)
    UNDO    undo · ignore that · scratch that · nvm · /undo
    RENAME  call this X · name it X · /name X
    DELETE  delete X · drop X · /delete X
    HELP    help · ? · /help · what can you do

Two rules worth defending when implementing:

`SWITCH` by bare integer — LIST returns a numbered list and the natural reply
to a numbered list is a number. Guard it: a bare integer is only a SWITCH when
the last outbound message to that user was a LIST, otherwise `4200` and `3` are
indistinguishable in intent and one of them is a price. That is what
`last_card_kind` in the user meta is for.

`SWITCH` matching order — exact nickname, then case-insensitive substring of
nickname, then substring of `title`, then list index. An ambiguous match returns
its candidates as a numbered list rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    RELAY = "RELAY"
    NEW = "NEW"
    LIST = "LIST"
    SWITCH = "SWITCH"
    CARD = "CARD"
    STATS = "STATS"
    CLOSE = "CLOSE"
    WALK = "WALK"
    UNDO = "UNDO"
    RENAME = "RENAME"
    DELETE = "DELETE"
    HELP = "HELP"


@dataclass
class Classification:
    """What the router decided, plus whatever the handler needs to act on it.

    `arg`   — the operand for SWITCH / RENAME / DELETE (a nickname, a title
              fragment, or a stringified list index). None for the rest.
    `url`   — the listing link, when intent is NEW.
    `price` — the price parsed out of a RELAY, when there was one. Present
              purely so callers can assert the price-beats-command rule held.
    `why`   — which rule fired, for tests and for the `/simulate` trace.
    """
    intent: Intent
    arg: Optional[str] = None
    url: Optional[str] = None
    price: Optional[float] = None
    why: str = "default"
    meta: dict = field(default_factory=dict)


# A price is any of: $5,400 · 5400 · 5.4k · 5,400 — the detector Lane B hardens.
# Kept module-level so tests and `main.py` can share one definition of "price".
PRICE_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?|\b\d[\d,]{2,}(?:\.\d+)?\b|\b\d+(?:\.\d+)?\s*k\b",
                      re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def has_price(text: Optional[str]) -> bool:
    """The one invariant that is frozen at stub time: price ⇒ relay."""
    return bool(text and PRICE_RE.search(text))


def classify(text: Optional[str],
             *,
             has_image: bool = False,
             last_card_kind: Optional[str] = None) -> Classification:
    """Route one inbound message.

    STUB — Lane B implements the command table. Until then this returns the
    safe default for every input, which is exactly the behaviour `main.py` has
    today: treat it as a seller relay. That makes the stub a no-op drop-in
    rather than a regression.

    `last_card_kind` is the previous outbound card type for this user
    ("list", "deal", "stats", …). It gates the bare-integer SWITCH rule.
    """
    if has_image:
        return Classification(Intent.RELAY, why="image")

    body = (text or "").strip()
    if not body:
        return Classification(Intent.RELAY, why="empty")

    # Frozen invariant, implemented now so the lanes can test against it.
    if has_price(body) and not body.startswith("/"):
        m = PRICE_RE.search(body)
        raw = m.group(0).lower().replace("$", "").replace(",", "").strip()
        try:
            price = float(raw[:-1]) * 1000 if raw.endswith("k") else float(raw)
        except ValueError:
            price = None
        return Classification(Intent.RELAY, price=price, why="price-beats-command")

    # A URL anywhere means a new deal. Cheap, unambiguous, safe to ship early.
    u = URL_RE.search(body)
    if u:
        return Classification(Intent.NEW, url=u.group(0), why="url")

    # TODO(Lane B): the command table above. Order matters — CLOSE/WALK reuse
    # CLOSE_KW/WALK_KW from main.py, and the bare-integer SWITCH must check
    # `last_card_kind == "list"` before firing.
    return Classification(Intent.RELAY, why="default")


__all__ = ["Intent", "Classification", "classify", "has_price", "PRICE_RE", "URL_RE"]
