"""Linq — the whole product surface (Partner API v3).

Closer has no dashboard, so this module is not "the messaging integration", it
is every affordance the user has. Text, tapbacks, typing indicators, screen
effects and image attachments all leave through here.

Send (POST /api/partner/v3/chats reuses/continues the chat with a participant):
    { "from": "+1205...", "to": ["+1..."],
      "message": { "parts": [ { "type": "text", "value": "..." } ],
                   "effect": { "name": "confetti", "type": "screen" } } }

Inbound webhook (event "message.received"):
    { "event_type": "message.received",
      "data": { "chat": {"id": "..."}, "id": "<message-id>", "direction": "inbound",
                "sender_handle": {"handle": "+1..."},
                "parts": [ {"type":"text","value":"..."}, {"type":"media","url":"..."} ] } }

Inbound tapback (events "reaction.added" / "reaction.removed"):
    { "event_type": "reaction.added",
      "data": { "chat_id": "...", "message_id": "<our message>", "reaction_type": "like",
                "is_from_me": false, "from": "+1...", "from_handle": {"handle": "+1..."} } }

━━ Endpoint map, read off @linqapp/sdk 2.5.0 and the live docs ━━━━━━━━━━━━━━━
    POST   /v3/chats                          send (creates or continues)
    POST   /v3/chats/{chat_id}/messages       send into a known chat
    POST   /v3/chats/{chat_id}/typing         typing indicator on
    DELETE /v3/chats/{chat_id}/typing         typing indicator off
    POST   /v3/messages/{message_id}/reactions   tapback add / remove
    POST   /v3/attachments                    presigned PUT + permanent id

━━ Failure policy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`send` and the attachment upload are load-bearing and raise `LinqError`. Every
decorative call — `react`, `typing`, `send_effect`'s effect part — is
fire-and-forget: it returns a status dict and never raises, because a tapback
that 500s must not cost a negotiation turn. Callers still wrap them, so a
failure is quiet at two layers.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

import httpx
from pydantic import BaseModel

LINQ_BASE_URL = os.getenv("LINQ_BASE_URL", "https://api.linqapp.com").rstrip("/")
LINQ_API_KEY = os.getenv("LINQ_API_KEY", "").strip()
LINQ_FROM_NUMBER = os.getenv("LINQ_FROM_NUMBER", "+12052611117").strip()
VERIFY_SIGNATURES = os.getenv("VERIFY_LINQ_SIGNATURES", "").lower() in ("1", "true", "yes")
LINQ_WEBHOOK_SECRET = os.getenv("LINQ_WEBHOOK_SECRET", "").strip()

_V3 = f"{LINQ_BASE_URL}/api/partner/v3"
_CHATS_URL = f"{_V3}/chats"

# §5.7: "Never send two bubbles under ~400ms apart" — they arrive out of order
# often enough to matter on stage. This is the floor for `send_bubbles`.
BUBBLE_GAP_SECONDS = float(os.getenv("LINQ_BUBBLE_GAP", "0.45"))

# The two effect families are a real distinction in the payload, not a label:
# `type` must agree with `name` or the effect is dropped silently.
SCREEN_EFFECTS = frozenset({
    "confetti", "fireworks", "lasers", "sparkles", "celebration", "hearts",
    "love", "balloons", "happy_birthday", "echo", "spotlight",
})
BUBBLE_EFFECTS = frozenset({"slam", "loud", "gentle", "invisible"})

# Standard iMessage tapbacks. Anything else has to ride as `custom` + an emoji.
REACTIONS = frozenset({"love", "like", "dislike", "laugh", "emphasize", "question"})


class LinqError(RuntimeError):
    pass


class InboundMessage(BaseModel):
    chat_id: Optional[str] = None
    message_id: Optional[str] = None        # what §5.1 reacts to, before inference
    sender: Optional[str] = None            # E.164 phone / handle
    text: Optional[str] = None
    media_urls: list[str] = []

    def has_content(self) -> bool:
        return bool(self.text or self.media_urls)


class InboundReaction(BaseModel):
    """A tapback on one of our messages (§5.2 — reactions as an input channel)."""
    chat_id: Optional[str] = None
    sender: Optional[str] = None
    message_id: Optional[str] = None
    reaction: Optional[str] = None           # like | love | question | emphasize | …
    emoji: Optional[str] = None              # set when reaction == "custom"
    removed: bool = False


class Attachment(BaseModel):
    """A file that now lives on Linq's CDN and can be sent any number of times."""
    attachment_id: str
    download_url: Optional[str] = None


def available() -> bool:
    return bool(LINQ_API_KEY)


def _headers() -> dict:
    return {"Authorization": f"Bearer {LINQ_API_KEY}",
            "Content-Type": "application/json"}


def _request(method: str, url: str, *, json: Optional[dict] = None,
             timeout: float = 30.0) -> dict:
    """One HTTP call against the Partner API. Raises `LinqError` on anything ≥400.

    Bodies come back empty for 204s (typing start/stop), so a non-JSON response
    with a 2xx status is success, not a parse failure.
    """
    if not LINQ_API_KEY:
        raise LinqError("LINQ_API_KEY not set — cannot reach Linq")
    r = httpx.request(method, url, headers=_headers(), json=json, timeout=timeout)
    if r.status_code >= 400:
        raise LinqError(f"Linq {method} {url} HTTP {r.status_code}: {r.text[:400]}")
    if not r.content:
        return {"ok": True, "status": r.status_code}
    try:
        return r.json()
    except Exception:
        return {"ok": True, "status": r.status_code, "raw": r.text[:400]}


def _quiet(fn, *args, **kwargs) -> dict:
    """Run a decorative call and swallow everything it can throw.

    The reason this exists rather than a `try/except` at each call site: these
    run on the critical path of a negotiation turn, and the failure mode we are
    defending against is not "the tapback didn't land", it is "the coach message
    never arrived because the tapback raised".
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:                              # noqa: BLE001 — deliberate
        return {"ok": False, "error": str(exc)[:200]}


# ── sending ──────────────────────────────────────────────────────────────────
def _effect_payload(effect: Optional[str]) -> Optional[dict]:
    """`"confetti"` → `{"name": "confetti", "type": "screen"}`, or None.

    An unknown name is dropped rather than guessed: sending `type: "screen"` for
    a bubble effect is a 400, and a rejected send costs the whole message.
    """
    if not effect:
        return None
    name = effect.strip().lower()
    if name in SCREEN_EFFECTS:
        return {"name": name, "type": "screen"}
    if name in BUBBLE_EFFECTS:
        return {"name": name, "type": "bubble"}
    return None


def _message_body(text: Optional[str], *, effect: Optional[str] = None,
                  attachment_id: Optional[str] = None,
                  media_url: Optional[str] = None) -> dict:
    """Assemble a `message` object.

    Part order is text-then-media on purpose: iMessage renders the caption above
    the image, which is how the deal card reads as "here is your card" rather
    than an unexplained chart. The API rejects consecutive text parts, so there
    is never more than one.
    """
    parts: list[dict] = []
    if text:
        parts.append({"type": "text", "value": text})
    if attachment_id:
        parts.append({"type": "media", "attachment_id": attachment_id})
    elif media_url:
        parts.append({"type": "media", "url": media_url})
    if not parts:
        raise LinqError("refusing to send an empty message")
    message: dict = {"parts": parts}
    fx = _effect_payload(effect)
    if fx:
        message["effect"] = fx
    return message


def send(to: str, text: Optional[str] = None, *, effect: Optional[str] = None,
         attachment_id: Optional[str] = None, media_url: Optional[str] = None,
         timeout: float = 30.0) -> dict:
    """Send an iMessage to a phone handle. Returns the API response JSON.

    Load-bearing: raises. `effect`, `attachment_id` and `media_url` are all
    optional upgrades on the same call — an unknown effect name degrades to a
    plain send instead of failing it.
    """
    body = {"from": LINQ_FROM_NUMBER, "to": [to],
            "message": _message_body(text, effect=effect,
                                     attachment_id=attachment_id, media_url=media_url)}
    return _request("POST", _CHATS_URL, json=body, timeout=timeout)


def send_effect(to: str, text: str, effect: str) -> dict:
    """Send with a screen effect — confetti on close, slam on a walk (§5.4).

    The effect is decoration; the message is not. If the API rejects the send
    outright we retry once without the effect, because "the deal closed" has to
    arrive even on the day Apple changes what `confetti` means.
    """
    try:
        return send(to, text, effect=effect)
    except LinqError:
        return send(to, text)


def sent_message_id(response: Optional[dict]) -> Optional[str]:
    """Pull our own message id out of a send response.

    Two shapes reach here: `POST /v3/chats` nests it under `chat.message`, and
    `POST /v3/chats/{id}/messages` returns `message` at the top. §5.2 needs this
    — a tapback names the message it landed on, so a message we never recorded
    is a tapback we cannot route.
    """
    if not isinstance(response, dict):
        return None
    for path in (("chat", "message", "id"), ("message", "id"), ("id",)):
        node: object = response
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, str) and node:
            return node
    return None


def send_bubbles(to: str, texts: Iterable[str], *, effect: Optional[str] = None,
                 gap: Optional[float] = None) -> list[Optional[str]]:
    """Send several short bubbles in order and return their message ids.

    §5.7 is the whole reason: the recommended number gets its own bubble so it
    is one long-press away from the clipboard, and bubbles closer than ~400ms
    apart arrive out of order often enough to matter in front of an audience.
    The effect, if any, rides on the last bubble — that is the one the user is
    looking at when it fires.
    """
    pause = BUBBLE_GAP_SECONDS if gap is None else gap
    bodies = [t for t in texts if t and t.strip()]
    ids: list[Optional[str]] = []
    for i, body in enumerate(bodies):
        if i:
            time.sleep(pause)
        last = i == len(bodies) - 1
        ids.append(sent_message_id(send(to, body, effect=effect if last else None)))
    return ids


# ── tapbacks (§5.1 out, §5.2 in) ─────────────────────────────────────────────
def react(message_id: str, type: str, emoji: Optional[str] = None) -> dict:  # noqa: A002
    """Tapback a message — ❗ bluff spotted, ❤️ deal closed.

    Decorative: never raises. It rides alongside a reply the user is waiting on,
    so it must never block one.
    """
    if not message_id:
        return {"ok": False, "error": "no message_id"}
    kind = (type or "").strip().lower()
    if kind not in REACTIONS and kind != "custom":
        kind, emoji = ("custom", emoji or type)
    body: dict = {"operation": "add", "type": kind}
    if kind == "custom":
        if not emoji:
            return {"ok": False, "error": "custom reaction needs an emoji"}
        body["custom_emoji"] = emoji
    return _quiet(_request, "POST", f"{_V3}/messages/{message_id}/reactions",
                  json=body, timeout=10.0)


def unreact(message_id: str, type: str) -> dict:  # noqa: A002
    """Remove a tapback we previously added. Decorative: never raises."""
    if not message_id:
        return {"ok": False, "error": "no message_id"}
    return _quiet(_request, "POST", f"{_V3}/messages/{message_id}/reactions",
                  json={"operation": "remove", "type": (type or "").strip().lower()},
                  timeout=10.0)


# ── typing indicator (§5.3) ──────────────────────────────────────────────────
def typing(chat_id: Optional[str], on: bool = True) -> dict:
    """Typing indicator, bracketing research and every LLM turn.

    Decorative: never raises. Group chats return 403 here and we do not use
    them; that 403 is swallowed like any other failure.
    """
    if not chat_id:
        return {"ok": False, "error": "no chat_id"}
    method = "POST" if on else "DELETE"
    return _quiet(_request, method, f"{_V3}/chats/{chat_id}/typing", timeout=10.0)


@contextmanager
def typing_while(chat_id: Optional[str]) -> Iterator[None]:
    """Hold a typing indicator for the duration of a slow block.

    Research runs ~30s and an LLM turn ~3s; in iMessage, silence for either
    reads as broken. The `finally` matters more than the `try`: an exception
    inside the block must still clear the indicator, or the thread is left
    showing us typing forever.
    """
    typing(chat_id, True)
    try:
        yield
    finally:
        typing(chat_id, False)


# ── attachments (§5.5) ───────────────────────────────────────────────────────
def _content_type_for(filename: str) -> str:
    guess, _ = mimetypes.guess_type(filename)
    return guess or "application/octet-stream"


def upload_bytes(data: bytes, filename: str,
                 content_type: Optional[str] = None) -> Attachment:
    """Two-step presigned upload: metadata → presigned PUT → permanent id.

    Load-bearing, so this raises. `required_headers` is not advisory — S3 signs
    over `content-length` and `content-type`, and omitting either fails the
    signature rather than the upload, which surfaces as a 403 with an XML body.
    """
    if not data:
        raise LinqError("refusing to upload an empty file")
    ctype = content_type or _content_type_for(filename)
    meta = _request("POST", f"{_V3}/attachments",
                    json={"filename": filename, "content_type": ctype,
                          "size_bytes": len(data)}, timeout=30.0)
    upload_url = meta.get("upload_url")
    attachment_id = meta.get("attachment_id")
    if not upload_url or not attachment_id:
        raise LinqError(f"Linq attachment metadata missing upload_url/attachment_id: {meta}")
    headers = dict(meta.get("required_headers") or {})
    headers.setdefault("Content-Type", ctype)
    headers.setdefault("Content-Length", str(len(data)))
    put = httpx.put(upload_url, content=data, headers=headers, timeout=60.0)
    if put.status_code >= 400:
        raise LinqError(f"Linq attachment PUT HTTP {put.status_code}: {put.text[:200]}")
    return Attachment(attachment_id=attachment_id, download_url=meta.get("download_url"))


def upload_attachment(file_path: str) -> Optional[str]:
    """Upload a file and return its permanent `attachment_id` (§4.7)."""
    path = Path(file_path)
    return upload_bytes(path.read_bytes(), path.name).attachment_id


def send_media(to: str, text: Optional[str], file_path: str) -> dict:
    """Send an image (the rendered deal card) as a real attachment."""
    path = Path(file_path)
    return send_media_bytes(to, text, path.read_bytes(), path.name)


def send_media_bytes(to: str, text: Optional[str], data: bytes, filename: str,
                     content_type: Optional[str] = None, *,
                     effect: Optional[str] = None) -> dict:
    """Upload bytes and send them in one call — the path `render.py` takes.

    Rendering produces bytes, so writing them to disk purely to read them back
    would be the only reason a temp file existed. The upload still happens
    because a media part needs either a public HTTPS URL or an `attachment_id`,
    and localhost is not a public URL.
    """
    attachment = upload_bytes(data, filename, content_type)
    return send(to, text, attachment_id=attachment.attachment_id, effect=effect)


# ── inbound parsing ──────────────────────────────────────────────────────────
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
        message_id=data.get("id"),
        sender=(data.get("sender_handle") or {}).get("handle"),
        text=text or None,
        media_urls=media,
    )


def parse_reaction(body: dict) -> Optional[InboundReaction]:
    """Return an InboundReaction for 'reaction.added' / 'reaction.removed', else None.

    Our own tapbacks echo back as events with `is_from_me: true` — §5.1 sends ❗
    on a bluff and ❤️ on a close, so without this guard every tapback we send
    would immediately re-enter as a user command.
    """
    if not isinstance(body, dict):
        return None
    event = body.get("event_type")
    if event not in ("reaction.added", "reaction.removed"):
        return None
    data = body.get("data") or {}
    if data.get("is_from_me"):
        return None
    handle = data.get("from") or (data.get("from_handle") or {}).get("handle")
    return InboundReaction(
        chat_id=data.get("chat_id"),
        sender=handle,
        message_id=data.get("message_id"),
        reaction=(data.get("reaction_type") or "").strip().lower() or None,
        emoji=data.get("custom_emoji"),
        removed=(event == "reaction.removed"),
    )


# ── webhook signature ────────────────────────────────────────────────────────
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
