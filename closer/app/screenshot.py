"""Screenshots of a chat — the relay path people actually use (§4.1, §7 A1).

Retyping what the seller said is a paragraph of work. Screenshotting the thread
is two taps, so that is what arrives: one image, or three images of the same
conversation scrolled to different places, usually with a caption like "what do
I say to this".

`app/llm.py` reads ONE image. This module turns a whole inbound message —
several images plus a caption — into the ordered list of *new* seller lines the
negotiation engine should replay, and nothing else. Pure orchestration over
`llm.read_screenshot`; the only I/O is the vision call it delegates.

━━ Three problems that only exist once there is more than one image ━━━━━━━━━━━

**Overlap.** Two screenshots of one thread share the middle of it — that is how
scrolling works. Replaying a shared message twice would update the posterior
twice on evidence that happened once, which is the exact failure mode the whole
product is built to *catch* a seller doing. So every line is fingerprinted and
first occurrence wins, both within one inbound message and against everything
this deal has already seen (`Deal.seen_screenshot_lines`).

**Order.** Images arrive in the order the user picked them, which is the order
they scrolled — oldest first. Lines are kept in that order and the engine
replays them in it, so the belief curve moves the same way it would have if the
user had relayed each message as it landed.

**Failure.** A blurry crop, a screenshot of a parking lot, a 403 on the media
URL: any of them can fail for one image while the others read fine. Failures are
counted, never fatal — `ok()` is what the caller branches on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from app import llm

#: Images read per inbound message. iMessage lets you attach a dozen; three
#: screenshots is already the whole conversation, and each one is a vision call
#: on the critical path of a live thread.
MAX_IMAGES = 4

#: Seller lines replayed from one inbound message. A screenshot of a long thread
#: can transcribe twenty bubbles, and replaying twenty turns off one message
#: would spend the whole negotiation in a single update. The *newest* lines are
#: the ones that carry information, so the cap keeps the tail.
MAX_NEW_LINES = 8

#: Fingerprints retained per deal. Enough to cover the overlap between any two
#: screenshots of the same thread without growing the stored deal without bound.
SEEN_LIMIT = 120

#: Shorter than this and there is nothing to classify — "ok", "👍", "?".
MIN_LINE_CHARS = 3

_FINGERPRINT_STRIP = re.compile(r"[^a-z0-9]+")


def fingerprint(text: str) -> str:
    """Identity of a message for dedupe: lowercase alphanumerics only.

    Deliberately lossy. The same bubble transcribed twice by a vision model
    differs in punctuation, curly-vs-straight apostrophes and stray whitespace
    far more often than it differs in words, and a fingerprint that those break
    would let the duplicate through — which is the failure that actually costs
    the user a wrong number.
    """
    return _FINGERPRINT_STRIP.sub("", (text or "").lower())


@dataclass
class ScreenshotRead:
    """Everything one inbound message's images turned out to contain."""

    kind: str = "other"                          # chat | listing | other
    seller_lines: list[str] = field(default_factory=list)   # new, ordered, deduped
    buyer_lines: list[str] = field(default_factory=list)
    latest_seller_price: Optional[float] = None
    asking: Optional[float] = None               # from a listing screenshot
    title: Optional[str] = None                  # "2008 Toyota Camry LE"
    images_read: int = 0
    images_failed: int = 0
    repeats: int = 0                             # lines this deal had already seen
    dropped: int = 0                             # lines over MAX_NEW_LINES
    error: Optional[str] = None                  # last failure, for the log

    def ok(self) -> bool:
        """At least one image was read and it was a car chat or a car listing."""
        return self.images_read > 0 and self.kind in ("chat", "listing")

    def has_new_lines(self) -> bool:
        return bool(self.seller_lines)

    def fingerprints(self) -> list[str]:
        """What to record on the deal once these lines have been replayed."""
        return [fingerprint(line) for line in self.seller_lines]

    def price_hint(self) -> Optional[float]:
        """The best guess at what this car costs, from a screenshot alone.

        A listing's asking price beats a seller's latest number: one is the
        anchor and the other is already a concession off it. Used only to start
        a deal that has no listing link (§7 A4), never to override research.
        """
        return self.asking or self.latest_seller_price


def _usable(text: str) -> bool:
    if len(text.strip()) < MIN_LINE_CHARS:
        return False
    return bool(re.search(r"[a-z0-9]", text.lower()))


def read(images: Iterable[str], *, caption: Optional[str] = None,
         seen: Optional[Iterable[str]] = None) -> ScreenshotRead:
    """Read every image on one inbound message into a single `ScreenshotRead`.

    `seen` is the deal's fingerprint history; lines matching it are counted as
    `repeats` and dropped, so re-sending an overlapping screenshot is a no-op
    rather than a second belief update on the same sentence.

    Never raises. A vision failure on one image is counted and the rest are
    still read, because the user's negotiation turn must not depend on the
    sharpest of their three screenshots being first.
    """
    out = ScreenshotRead()
    refs = [r for r in (images or []) if r][:MAX_IMAGES]
    if not refs:
        return out

    known = set(seen or ())
    within: set[str] = set()
    kinds: list[str] = []

    for ref in refs:
        try:
            payload = llm.read_screenshot(ref, caption=caption)
        except Exception as exc:                  # noqa: BLE001 — vision is best-effort
            out.images_failed += 1
            out.error = str(exc)[:200]
            continue

        out.images_read += 1
        kinds.append(payload["kind"])
        if payload["latest_seller_price"] is not None:
            out.latest_seller_price = payload["latest_seller_price"]
        if payload["asking"] is not None:
            out.asking = payload["asking"]
        if payload["title"] and not out.title:
            out.title = payload["title"]

        for message in payload["messages"]:
            text = message["text"]
            if not _usable(text):
                continue
            if message["from"] == "buyer":
                out.buyer_lines.append(text)
                continue
            key = fingerprint(text)
            if key in within:
                continue                          # the same image listed it twice
            within.add(key)
            if key in known:
                out.repeats += 1
                continue
            out.seller_lines.append(text)

    # `chat` wins over `listing` wins over `other`: one readable chat among three
    # images is a chat, and one readable listing among three unreadable crops is
    # still enough to start a deal.
    for candidate in ("chat", "listing"):
        if candidate in kinds:
            out.kind = candidate
            break

    if len(out.seller_lines) > MAX_NEW_LINES:
        out.dropped = len(out.seller_lines) - MAX_NEW_LINES
        out.seller_lines = out.seller_lines[-MAX_NEW_LINES:]
    return out


def remember(previous: Iterable[str], added: Iterable[str]) -> list[str]:
    """Append fingerprints to a deal's history, deduped and bounded."""
    out = list(previous or ())
    known = set(out)
    for key in added:
        if key and key not in known:
            known.add(key)
            out.append(key)
    return out[-SEEN_LIMIT:]


__all__ = ["ScreenshotRead", "read", "remember", "fingerprint",
           "MAX_IMAGES", "MAX_NEW_LINES", "SEEN_LIMIT"]
