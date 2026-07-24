"""Intent router — the command grammar from update_1.md §4.1.

Pure. No I/O, no LLM, no import from `main`. One regex pass over one string.

━━ The hard rule ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    If a message contains a price, it is a seller relay. Never a command.

~90% of real traffic is "he said 5400". Misrouting a relay into a command
breaks a live negotiation, so RELAY is the default for everything unmatched.

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

━━ Three orderings that are decisions, not accidents ━━━━━━━━━━━━━━━━━━━━━━━━━

**A URL beats a price.** §4.1 lists both "anything with a price → RELAY" and "a
URL anywhere → NEW" without saying which wins, and real messages contain both:
the Facebook Marketplace share sheet produces `$6,400 · 2008 Toyota Camry LE
https://…` verbatim. If price won, every share-sheet paste — the entire
onboarding flow and acceptance steps 2 and 5 — would be swallowed as a seller
relay against a deal that does not exist yet. So URL is checked first. The cost
is that relaying a seller message which happens to contain a link creates a deal
instead; that is rare, recoverable with `delete`, and the far smaller error.

**A bare integer is a SWITCH only right after a LIST.** `LIST` returns a
numbered list and the natural reply to a numbered list is a number, so it is the
cheapest possible context switch — one character. But `3` and `4200` are
indistinguishable in intent and one of them is a price, so the rule is gated on
`last_card_kind == "list"`. Outside that window a bare number is a relay, which
is also exactly what `llm.extract_price` assumes (it reads bare `3` as $3,000).

**CLOSE is matched last and narrowly.** `main.py:50` has the bare word `deal` in
`CLOSE_KW` and tests it with `in`, which also fires on "deals" (a LIST), "the
Camry deal" (a SWITCH) and "no deal" (a WALK). Here `deal` alone closes a deal
only when it *is* the message, modulo filler — "deal", "ok deal", "yes deal!".
Every multi-word close phrase still matches anywhere with word boundaries.

━━ SWITCH resolution is the caller's job ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`classify` returns the raw operand in `Classification.arg`; it has no deal list
and cannot resolve it. `resolve_switch` below implements the §4.1 matching order
— exact nickname, case-insensitive nickname substring, title substring, list
index — and returns the candidates when a match is ambiguous so the caller can
ask rather than guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence


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


# A price is any of: $5,400 · 5400 · 5.4k · 5,400 — one definition, shared by
# the tests and by `main.py`.
#
# The lookarounds on the bare-number branch exist because model names are full
# of three-digit runs: `F-150`, `C-300`, `Model 3`. Without them "drop the
# F-150" reads as a $150 relay and the command is unreachable. A digit run
# glued to a word character or a hyphen is part of a name, not a price.
#
# Four-digit years ARE still read as prices ("the 2008 Camry deal" -> RELAY).
# That is deliberate: $2,008 is a plausible number for a beater and the hard
# rule says ambiguity resolves toward RELAY. `/switch 2008 Camry` is the hatch.
PRICE_RE = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d+)?"                          # $5,400 · $ 5400
    r"|(?<![\w$.\-])\d[\d,]{2,}(?:\.\d+)?(?![\w\-])"    # 5,400 · 5400 · 1,200.50
    r"|(?<![\w$.\-])\d+(?:\.\d+)?\s*k\b",               # 5.4k · 13.5K
    re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# A bare list index. §4.1 caps it at 10 because §3 caps a phone at 10 deals, and
# because every integer above that is far more likely to be money.
BARE_INDEX_RE = re.compile(r"^#?\s*(10|[1-9])[.)]?$")

# Filler that can wrap a one-word command without changing it: "ok deal",
# "yeah stats", "hey help". Stripped before the whole-message equality tests.
_FILLER = {"ok", "okay", "k", "kk", "yes", "yep", "yeah", "yup", "sure", "cool",
           "great", "nice", "please", "pls", "plz", "hey", "hi", "hello", "yo",
           "thanks", "thx", "ty", "alright", "aight", "and", "so", "well", "just"}

_PUNCT = " \t\n.,!?…:;-–—\"'`*"


def _norm(text: str) -> str:
    """Lowercase, collapse whitespace, drop trailing punctuation."""
    return re.sub(r"\s+", " ", text.lower()).strip(_PUNCT).strip()


def _core(text: str) -> tuple[str, str]:
    """Whitespace-collapsed, punctuation-trimmed, leading/trailing filler dropped.

    Returns `(lowercased, original-case)` — the same string twice, differing
    only in case. Matching is done on the lowercased copy; operands are sliced
    out of the cased one, because `call this the Red Civic` has to keep its
    capitals when it becomes a nickname.

    "ok deal!" -> ("deal", "deal").  "hey What Can You Do" -> ("what can you do", …).
    """
    words = [w.strip(_PUNCT) for w in re.sub(r"\s+", " ", text.strip()).split()]
    words = [w for w in words if w]
    while words and words[0].lower() in _FILLER:
        words.pop(0)
    while words and words[-1].lower() in _FILLER:
        words.pop()
    cased = " ".join(words)
    return cased.lower(), cased


def _operand(match: "re.Match[str]", cased: str) -> Optional[str]:
    """Pull group 1 out of the original-case string using the lowercase match's
    offsets. Falls back to the lowercase text if a locale-specific `.lower()`
    changed the length (Turkish dotted I and friends), which is never worse than
    what we'd have had otherwise."""
    lowered = match.string
    if len(lowered) == len(cased):
        return cased[match.start(1):match.end(1)]
    return match.group(1)


def _phrase(text: str, phrases: Sequence[str]) -> Optional[str]:
    """First phrase that appears in `text` on word boundaries, else None."""
    for p in phrases:
        if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text):
            return p
    return None


# ── the tables ───────────────────────────────────────────────────────────────
# `_EXACT_*` match the whole message (after filler stripping). `_ANY_*` match
# anywhere on word boundaries and are reserved for phrases long enough that a
# false positive is implausible.

_EXACT_HELP = {"help", "?", "??", "h", "what can you do", "what can u do",
               "what do you do", "how does this work", "how do i use this",
               "what is this", "who are you", "commands", "menu"}
_ANY_HELP = ("what can you do", "how does this work", "what can you help")

_EXACT_LIST = {"deals", "my deals", "list", "list deals", "all deals", "show deals",
               "show my deals", "list my deals", "open deals", "what deals",
               "what am i working on", "what am i running", "which deals",
               "what do i have going", "everything"}
_ANY_LIST = ("what am i working on", "list my deals", "show me my deals",
             "what deals do i have", "what am i running")

_EXACT_STATS = {"stats", "savings", "total", "totals", "my stats", "lifetime",
                "how much have i saved", "how much did i save", "how much have we saved",
                "how am i doing", "score", "scoreboard", "receipts"}
_ANY_STATS = ("how much have i saved", "how much did i save", "how much have we saved",
              "how much money have i saved", "lifetime savings", "total savings")

_EXACT_CARD = {"card", "status", "where are we", "where we at", "show me", "the curve",
               "curve", "recap", "state of play", "where am i", "whats the status",
               "what's the status", "where do we stand", "show me the card",
               "current", "update", "sitrep"}
_ANY_CARD = ("where are we", "where do we stand", "show me the card", "the belief curve",
             "whats the status", "what's the status", "state of play")

_EXACT_UNDO = {"undo", "nvm", "nevermind", "never mind", "ignore that", "scratch that",
               "disregard", "my bad", "oops", "wrong", "take that back", "undo that",
               "ignore my last", "scratch it", "delete that"}
_ANY_UNDO = ("ignore that", "scratch that", "take that back", "ignore my last",
             "forget what i said", "undo that")

# CLOSE / WALK, split by how safely each phrase can match mid-sentence.
# The multi-word ones are unambiguous anywhere; the one-word ones must BE the
# message. `main.py:50`'s bare "deal" is the reason this split exists.
_ANY_CLOSE = ("we have a deal", "we've got a deal", "weve got a deal", "done deal",
              "it's a deal", "its a deal", "i'll take it", "ill take it",
              "i will take it", "we agreed", "closing at", "closed at",
              "shook on it", "handed over the cash", "bought the car")
_EXACT_CLOSE = {"deal", "sold", "done", "closed", "took it", "bought it",
                "picked it up", "i took it", "i bought it", "we closed", "signed"}

_ANY_WALK = ("i walked away", "walked away", "walk away", "i'm walking", "im walking",
             "i am walking", "passed on it", "i passed on it", "no deal",
             "found another", "found a better one", "backed out", "not buying it",
             "not worth it", "moving on")
_EXACT_WALK = {"walked", "i walked", "i passed", "pass", "passed", "walk",
               "i'm out", "im out", "out", "forget it", "let it go"}

# Operand commands. Each captures the rest of the message as `arg`.
_RENAME_RE = re.compile(
    r"^(?:call (?:this|it|that)|name (?:this|it|that)|rename (?:this|it|that)?|"
    r"label (?:this|it|that)|lets call (?:this|it)|let's call (?:this|it))\s+(.+)$")
_DELETE_RE = re.compile(r"^(?:delete|drop|remove|kill|forget|trash|nuke)\s+(.+)$")
_SWITCH_RE = re.compile(
    r"^(?:switch (?:to|over to)|go (?:to|back to)|back to|open|pull up|focus (?:on)?|"
    r"work on|jump to|show(?: me)?)\s+(.+)$")
# Last-resort SWITCH: "the Camry deal", "camry deal", "the camry one".
_TRAILING_DEAL_RE = re.compile(r"^(?:the\s+)?(.{1,40}?)\s+(?:deal|one|car)$")

# Slash commands. The escape hatch: a leading `/` forces command interpretation,
# so `/switch 4200` reaches SWITCH even though it contains a price.
_SLASH = {
    "deals": Intent.LIST, "list": Intent.LIST,
    "card": Intent.CARD, "status": Intent.CARD, "curve": Intent.CARD,
    "stats": Intent.STATS, "savings": Intent.STATS,
    "help": Intent.HELP, "h": Intent.HELP,
    "undo": Intent.UNDO,
    "close": Intent.CLOSE, "walk": Intent.WALK,
    "switch": Intent.SWITCH, "go": Intent.SWITCH,
    "name": Intent.RENAME, "rename": Intent.RENAME,
    "delete": Intent.DELETE, "drop": Intent.DELETE,
    "new": Intent.NEW, "relay": Intent.RELAY, "say": Intent.RELAY,
}
_SLASH_TAKES_ARG = {Intent.SWITCH, Intent.RENAME, Intent.DELETE, Intent.NEW, Intent.RELAY}

_ARTICLES = ("the ", "my ", "that ", "a ", "an ")

# A deal name is short and is not a question. These guard the SWITCH and DELETE
# operands so "show me what he said" and "forget what he told you" fall through
# to RELAY instead of being read as a deal called "what he said". RENAME is
# deliberately not guarded — the user picks that string and may pick anything.
_MAX_NAME_WORDS = 5
_NOT_A_NAME_HEAD = {"what", "where", "when", "why", "who", "how", "whether",
                    "if", "me", "us", "him", "her", "them", "it", "this", "that",
                    "everything", "anything", "something"}


def _looks_like_a_name(arg: Optional[str]) -> bool:
    if not arg:
        return False
    words = arg.split()
    if len(words) > _MAX_NAME_WORDS:
        return False
    return words[0].lower() not in _NOT_A_NAME_HEAD


def has_price(text: Optional[str]) -> bool:
    """The one invariant that is frozen at stub time: price ⇒ relay."""
    return bool(text and PRICE_RE.search(text))


def parse_price(text: Optional[str]) -> Optional[float]:
    """First price in `text` as a float, or None. `5.4k` -> 5400.0."""
    m = PRICE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(0).lower().replace("$", "").replace(",", "").strip()
    try:
        return float(raw[:-1].strip()) * 1000 if raw.endswith("k") else float(raw)
    except ValueError:                                  # pragma: no cover - defensive
        return None


def _clean_arg(arg: Optional[str]) -> Optional[str]:
    """Trim an operand down to the name the user meant: drop articles, quotes,
    trailing 'deal'/'one', and any trailing punctuation."""
    if arg is None:
        return None
    a = arg.strip().strip("\"'“”‘’ ").strip(_PUNCT).strip()
    low = a.lower()
    for art in _ARTICLES:
        if low.startswith(art):
            a, low = a[len(art):].strip(), low[len(art):].strip()
            break
    for tail in (" deal", " one", " car", " listing"):
        if low.endswith(tail):
            a = a[: -len(tail)].strip()
            break
    a = a.strip(_PUNCT).strip()
    return a or None


def classify(text: Optional[str],
             *,
             has_image: bool = False,
             last_card_kind: Optional[str] = None,
             awaiting_asking: bool = False) -> Classification:
    """Route one inbound message.

    `last_card_kind` is the previous outbound card type for this user
    ("list", "deal", "stats", …). It gates the bare-integer SWITCH rule.

    `awaiting_asking` is the §7 A4 research-blocked state: the listing 403'd and
    we asked "what are they asking?", so the next bare number is that price and
    must reach the negotiation path rather than being read as a list index. It
    is the one documented exception to the bare-integer SWITCH rule, and it is
    off by default so a caller that never sets it cannot be surprised by it.
    """
    if has_image:
        # An image is always evidence about a seller, never a command. §4.1.
        return Classification(Intent.RELAY, why="image")

    body = (text or "").strip()
    if not body:
        return Classification(Intent.RELAY, why="empty")

    # "?" survives nothing downstream — `_norm` strips trailing punctuation, so
    # a message that is *only* punctuation normalises to the empty string. Catch
    # the one punctuation-only command the grammar has before that happens.
    if set(body) <= {"?"}:
        return Classification(Intent.HELP, why="help:punctuation")

    # ── 1. slash escape hatch ────────────────────────────────────────────────
    # Checked before everything, including the price rule: `/switch 4200` is a
    # deliberate override and the leading slash is how the user says so.
    if body.startswith("/"):
        head, _, tail = body[1:].strip().partition(" ")
        kind = _SLASH.get(head.lower().strip(_PUNCT))
        if kind is not None:
            arg = tail.strip() or None
            if kind is Intent.NEW:
                u = URL_RE.search(tail)
                return Classification(Intent.NEW, url=u.group(0) if u else None,
                                      why="slash:new")
            if kind is Intent.RELAY:
                # `/say he came down to 5,400` — force a relay even if the body
                # would otherwise read as a command. `meta.text` is the payload
                # with the slash verb stripped.
                return Classification(Intent.RELAY, price=parse_price(tail),
                                      why="slash:relay", meta={"text": arg})
            if kind in _SLASH_TAKES_ARG:
                return Classification(kind, arg=_clean_arg(arg), why=f"slash:{head.lower()}")
            return Classification(kind, why=f"slash:{head.lower()}")
        # Unknown slash command — fall through. Better a relay than a 404.

    # ── 2. a URL means a new deal ────────────────────────────────────────────
    # Before the price rule, on purpose: see the module docstring.
    u = URL_RE.search(body)
    if u:
        return Classification(Intent.NEW, url=u.group(0), price=parse_price(body),
                              why="url")

    core, cased = _core(body)
    norm = _norm(body)

    # ── 3. bare list index, only in the window right after a LIST ────────────
    m = BARE_INDEX_RE.match(core)
    if m and not awaiting_asking:
        if last_card_kind == "list":
            return Classification(Intent.SWITCH, arg=m.group(1), why="bare-index")
        # No list on screen: a lone number is money. Fall through to RELAY.
        return Classification(Intent.RELAY, price=parse_price(core),
                              why="bare-int-no-list")

    # ── 4. the hard rule: a price is a relay ─────────────────────────────────
    if has_price(body):
        return Classification(Intent.RELAY, price=parse_price(body),
                              why="price-beats-command")

    # ── 5. the command table, ordered so the specific beats the general ──────
    if core in _EXACT_HELP or _phrase(norm, _ANY_HELP):
        return Classification(Intent.HELP, why="help")

    if core in _EXACT_LIST or _phrase(norm, _ANY_LIST):
        return Classification(Intent.LIST, why="list")

    if core in _EXACT_STATS or _phrase(norm, _ANY_STATS):
        return Classification(Intent.STATS, why="stats")

    if core in _EXACT_CARD or _phrase(norm, _ANY_CARD):
        return Classification(Intent.CARD, why="card")

    if core in _EXACT_UNDO or _phrase(norm, _ANY_UNDO):
        return Classification(Intent.UNDO, why="undo")

    m = _RENAME_RE.match(core)
    if m:
        # A nickname keeps the user's capitals — it goes straight onto a card.
        return Classification(Intent.RENAME, arg=_clean_arg(_operand(m, cased)),
                              why="rename")

    m = _DELETE_RE.match(core)
    if m:
        arg = _clean_arg(_operand(m, cased))
        # "delete that" is an UNDO, not a DELETE — caught above by _EXACT_UNDO,
        # but "drop it" / "forget it" land here with a pronoun operand.
        if arg is None or arg.lower() in ("it", "this", "that", "them"):
            return Classification(Intent.UNDO, why="undo:pronoun-delete")
        if _looks_like_a_name(arg):
            return Classification(Intent.DELETE, arg=arg, why="delete")
        # "forget what he told you" is not a deal name. Fall through.

    m = _SWITCH_RE.match(core)
    if m:
        arg = _clean_arg(_operand(m, cased))
        if _looks_like_a_name(arg):
            return Classification(Intent.SWITCH, arg=arg, why="switch")

    # WALK before CLOSE: `main.py:109 _detect_outcome` tests walk first because
    # "no deal" contains "deal", and that ordering is load-bearing.
    if core in _EXACT_WALK or _phrase(norm, _ANY_WALK):
        return Classification(Intent.WALK, why="walk")

    if core in _EXACT_CLOSE or _phrase(norm, _ANY_CLOSE):
        return Classification(Intent.CLOSE, why="close")

    # ── 6. last-resort SWITCH: "the Camry deal" ──────────────────────────────
    # After CLOSE/WALK so "we have a deal" is never read as switching to the
    # deal named "we have a".
    m = _TRAILING_DEAL_RE.match(core)
    if m:
        arg = _clean_arg(_operand(m, cased))
        if _looks_like_a_name(arg) and arg.lower() not in _FILLER:
            return Classification(Intent.SWITCH, arg=arg, why="switch:trailing-noun")

    return Classification(Intent.RELAY, why="default")


# ── SWITCH resolution (§4.1) ─────────────────────────────────────────────────
def _label(deal) -> str:
    return (getattr(deal, "nickname", None) or getattr(deal, "title", "") or "").strip()


def resolve_switch(arg: Optional[str], deals: Sequence) -> tuple[Optional[object], list]:
    """Resolve a SWITCH operand against the user's deals.

    Returns `(deal, candidates)`. Exactly one of them is meaningful:

        (deal, [])          unambiguous — switch to it
        (None, [a, b])      ambiguous — ask, with these as the numbered options
        (None, [])          nothing matched

    Matching order is §4.1: exact nickname, case-insensitive nickname substring,
    substring of `title`, then list index. Each tier is tried in full before the
    next, so a deal literally nicknamed "civic" always beats one merely titled
    "2016 Honda Civic EX". Ambiguity is returned, never guessed.

    `deals` must be in the same order the user last saw in a LIST card, because
    the index tier resolves against exactly that ordering.
    """
    needle = (arg or "").strip().lower()
    # An empty needle is a substring of every title. Without this guard a
    # whitespace operand silently "matches" whichever deal happens to be first.
    if not needle or not deals:
        return None, []

    exact = [d for d in deals if _label(d).lower() == needle]
    if len(exact) == 1:
        return exact[0], []
    if exact:
        return None, exact

    nick = [d for d in deals
            if getattr(d, "nickname", None) and needle in d.nickname.lower()]
    if len(nick) == 1:
        return nick[0], []
    if nick:
        return None, nick

    title = [d for d in deals if needle in (getattr(d, "title", "") or "").lower()]
    if len(title) == 1:
        return title[0], []
    if title:
        return None, title

    if needle.isdigit():
        i = int(needle)
        if 1 <= i <= len(deals):
            return deals[i - 1], []

    return None, []


__all__ = ["Intent", "Classification", "classify", "resolve_switch",
           "has_price", "parse_price", "PRICE_RE", "URL_RE", "BARE_INDEX_RE"]
