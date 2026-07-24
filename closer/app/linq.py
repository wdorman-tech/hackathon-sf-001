"""Linq — iMessage send + inbound webhook parsing (Partner API v3).

Send (POST /api/partner/v3/chats reuses/continues the chat with a participant):
    { "from": "+1205...", "to": ["+1..."],
      "message": { "parts": [ { "type": "text", "value": "..." } ] } }

Inbound webhook (event "message.received"):
    { "event_type": "message.received",
      "data": { "chat": {"id": "..."}, "direction": "inbound",
                "sender_handle": {"handle": "+1..."},
                "parts": [ {"type":"text","value":"..."}, {"type":"media","url":"..."} ] } }
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

import httpx
from pydantic import BaseModel

LINQ_BASE_URL = os.getenv("LINQ_BASE_URL", "https://api.linqapp.com").rstrip("/")
LINQ_API_KEY = os.getenv("LINQ_API_KEY", "").strip()
LINQ_FROM_NUMBER = os.getenv("LINQ_FROM_NUMBER", "+12052611117").strip()
VERIFY_SIGNATURES = os.getenv("VERIFY_LINQ_SIGNATURES", "").lower() in ("1", "true", "yes")
LINQ_WEBHOOK_SECRET = os.getenv("LINQ_WEBHOOK_SECRET", "").strip()

_CHATS_URL = f"{LINQ_BASE_URL}/api/partner/v3/chats"


class LinqError(RuntimeError):
    pass


class InboundMessage(BaseModel):
    chat_id: Optional[str] = None
    sender: Optional[str] = None            # E.164 phone / handle
    text: Optional[str] = None
    media_urls: list[str] = []

    def has_content(self) -> bool:
        return bool(self.text or self.media_urls)


def available() -> bool:
    return bool(LINQ_API_KEY)


def send(to: str, text: str, *, timeout: float = 30.0) -> dict:
    """Send an iMessage to a phone handle. Returns the API response JSON."""
    if not LINQ_API_KEY:
        raise LinqError("LINQ_API_KEY not set — cannot send")
    body = {
        "from": LINQ_FROM_NUMBER,
        "to": [to],
        "message": {"parts": [{"type": "text", "value": text}]},
    }
    r = httpx.post(_CHATS_URL,
                   headers={"Authorization": f"Bearer {LINQ_API_KEY}",
                            "Content-Type": "application/json"},
                   json=body, timeout=timeout)
    if r.status_code >= 400:
        raise LinqError(f"Linq send HTTP {r.status_code}: {r.text[:400]}")
    return r.json()


# ── seam 2: the iMessage-native surface (§4.7) ───────────────────────────────
# Frozen at Sync 1 as no-ops so `main.py` can wire the call sites now and Dev 2
# fills the bodies in Phase 2. Every one of these is fire-and-forget decoration:
# a tapback that fails must never cost a negotiation turn, so they return a
# status dict instead of raising, and callers still wrap them in try/except.
#
# All four are verified to exist on the CLI (LINQ.md, Phase 0 probes, closer
# profile). The REST shapes on Partner API v3 are not, so `subprocess` to
# `linq ... --profile closer` is the guaranteed fallback for the real bodies.
_STUB = {"ok": False, "stub": True}


class InboundReaction(BaseModel):
    """A tapback on one of our messages (§5.2 — reactions as an input channel)."""
    chat_id: Optional[str] = None
    sender: Optional[str] = None
    message_id: Optional[str] = None
    reaction: Optional[str] = None           # like | love | question | exclaim | …
    removed: bool = False


def upload_attachment(file_path: str) -> Optional[str]:
    """Upload bytes, return the permanent `download_url`. Stub until Phase 2.

    CLI: `linq attachments upload --filename --content-type --size` hands back a
    presigned PUT plus a `download_url`; you upload the bytes yourself.
    """
    del file_path
    return None


def send_media(to: str, text: Optional[str], file_path: str) -> dict:
    """Send an image (the rendered deal card) as a real attachment. Stub."""
    del to, text, file_path
    return dict(_STUB)


def react(message_id: str, type: str, emoji: Optional[str] = None) -> dict:  # noqa: A002
    """Tapback a message — 👍 logged, ❗ bluff spotted, ❓ couldn't parse. Stub.

    CLI: `linq messages react <message-id> --type like` (`--operation remove`).
    """
    del message_id, type, emoji
    return dict(_STUB)


def typing(chat_id: str, on: bool = True) -> dict:
    """Typing indicator, bracketing research and every LLM turn. Stub.

    CLI: `linq chats typing <chat-id>` / `--stop`.
    """
    del chat_id, on
    return dict(_STUB)


def send_effect(to: str, text: str, effect: str) -> dict:
    """Send with a screen effect — confetti on close, slam on a walk. Stub.

    CLI: `linq messages send <chat-id> --message "🎉" --effect confetti`.
    """
    del effect
    return send(to, text) if LINQ_API_KEY else dict(_STUB)


def parse_reaction(body: dict) -> Optional[InboundReaction]:
    """Inbound `reaction.added` / `reaction.removed`. Stub until Phase 2."""
    del body
    return None


def parse_webhook(body: dict) -> Optional[InboundMessage]:
    """Return an InboundMessage for inbound 'message.received' events, else None
    (reactions, typing, delivery receipts, and our own outbound echoes are ignored)."""
    if not isinstance(body, dict) or body.get("event_type") != "message.received":
        return None
    data = body.get("data") or {}
    if data.get("direction") not in (None, "inbound"):
        return None
    parts = data.get("parts") or []
    text = " ".join(p.get("value", "") for p in parts
                    if p.get("type") == "text" and p.get("value")).strip()
    media = [p["url"] for p in parts if p.get("type") == "media" and p.get("url")]
    return InboundMessage(
        chat_id=(data.get("chat") or {}).get("id"),
        sender=(data.get("sender_handle") or {}).get("handle"),
        text=text or None,
        media_urls=media,
    )


def signatures_enforced() -> bool:
    """Verification is on if explicitly enabled OR a secret is configured.

    A configured LINQ_WEBHOOK_SECRET is never silently ignored: forgetting to also
    flip VERIFY_LINQ_SIGNATURES used to leave the webhook wide open, and an open
    webhook lets anyone who knows the URL drive a negotiation, burn Runware credit,
    and aim the research agent's outbound fetches. Demo default (no secret set at
    all) is still unverified, as the build spec calls for.
    """
    return VERIFY_SIGNATURES or bool(LINQ_WEBHOOK_SECRET)


def verify_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC check for x-webhook-signature. See signatures_enforced() for the gate."""
    if not signatures_enforced():
        return True
    if not (signature and LINQ_WEBHOOK_SECRET):
        return False
    expected = hmac.new(LINQ_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature.split("=")[-1].strip()
    return hmac.compare_digest(expected, provided)
