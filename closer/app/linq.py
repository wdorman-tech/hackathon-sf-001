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


def verify_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC check for x-webhook-signature. Only enforced when VERIFY_LINQ_SIGNATURES=true."""
    if not VERIFY_SIGNATURES:
        return True
    if not (signature and LINQ_WEBHOOK_SECRET):
        return False
    expected = hmac.new(LINQ_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature.split("=")[-1].strip()
    return hmac.compare_digest(expected, provided)
