"""Runware native task API client (text + vision), over httpx.

Runware speaks a single endpoint that takes a JSON ARRAY of task objects:

    POST https://api.runware.ai/v1
    Authorization: Bearer $RUNWARE_API_KEY
    [ { "taskType": "textInference", "taskUUID": "...", "model": "...",
        "messages": [ {"role": "user", "content": "..."} ],
        "settings": { "maxTokens": 1024, "temperature": 0 } } ]
    -> { "data": [ { "taskType": "textInference", "taskUUID": "...",
                     "text": "...", "finishReason": "stop", "cost": 0.0005 } ] }

One AIR model id (`anthropic:claude@sonnet-4.6`) does BOTH text and image->text,
so the same call powers classify / draft / screenshot extraction. We deliberately
use the native task API rather than the OpenAI /v1/chat/completions shim, because
the shim is text-only (no image inputs).

Images are NOT a top-level `images` key — that returns unsupportedParameter. They
ride as Anthropic-style content parts on the last user message; see _image_part.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import uuid
from typing import Optional

import httpx

BASE_URL = os.getenv("RUNWARE_BASE_URL", "https://api.runware.ai/v1").rstrip("/")
API_KEY = os.getenv("RUNWARE_API_KEY", "").strip()
MODEL = os.getenv("RUNWARE_MODEL", "anthropic:claude@sonnet-4.6").strip()

#: Anthropic's long-edge limit. A phone screenshot is 3–5 MB and gets rejected.
MAX_IMAGE_EDGE = 1568

#: The only media types Anthropic accepts for an image block.
_ALLOWED_MEDIA = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class RunwareError(RuntimeError):
    """Any non-success from the Runware API (HTTP error or task-level error)."""


def available() -> bool:
    """True when a key is configured — gates the LLM path vs the rules fallback."""
    return bool(API_KEY)


# ── vision plumbing ──────────────────────────────────────────────────────────
#
# Three shapes were probed against the live API. Only one works:
#
#   task["images"] = [...]                                  unsupportedParameter
#   content: [{type:"image_url", image_url:{url}}]          providerBadRequest
#   content: [{type:"image", source:{type:"base64", ...}}]  ✅
#   source: {type:"url", url}                               providerBadRequest
#
# So images ride as Anthropic-style content parts on the last *user* message,
# and any URL — including the Linq media URLs inbound screenshots arrive as —
# must be downloaded and inlined. `llm.py` callers keep passing `images=[...]`.


def _sniff_media(raw: bytes, declared: str) -> str:
    """Trust the declared type only if Anthropic accepts it; else read the magic bytes.

    Linq media URLs frequently serve `application/octet-stream`.
    """
    declared = (declared or "").lower().strip()
    if declared == "image/jpg":                      # common mislabel
        declared = "image/jpeg"
    if declared in _ALLOWED_MEDIA:
        return declared
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _downscale(raw: bytes, media: str) -> tuple[bytes, str]:
    """Cap the long edge at MAX_IMAGE_EDGE, re-encoding as JPEG.

    Degrades to a pass-through if Pillow is missing or the image won't decode —
    a resize failure must never cost the user their negotiation turn.
    """
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return raw, media
    try:
        im = Image.open(io.BytesIO(raw))
        if max(im.size) <= MAX_IMAGE_EDGE:
            return raw, media
        im.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, media


def _image_part(ref: str, *, timeout: float = 30.0) -> dict:
    """URL | data URI | raw base64 -> an Anthropic-style image content part."""
    try:
        if ref.startswith("data:"):
            header, _, b64 = ref.partition(",")
            declared = header[5:].split(";")[0]
            raw = base64.b64decode(b64, validate=False)
        elif ref.startswith(("http://", "https://")):
            r = httpx.get(ref, timeout=timeout, follow_redirects=True)
            r.raise_for_status()
            declared = (r.headers.get("content-type") or "").split(";")[0]
            raw = r.content
        else:
            declared, raw = "", base64.b64decode(ref, validate=False)
    except httpx.HTTPError as e:
        raise RunwareError(f"could not fetch image {ref[:80]}: {e}") from e
    except (binascii.Error, ValueError) as e:
        raise RunwareError(f"image is not valid base64: {e}") from e

    if not raw:
        raise RunwareError(f"image {ref[:80]} was empty")

    media = _sniff_media(raw, declared)
    raw, media = _downscale(raw, media)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media,
            "data": base64.b64encode(raw).decode(),
        },
    }


def _attach_images(turns: list[dict], images: list[str]) -> None:
    """Fold image parts onto the last user turn, in place.

    Anthropic only accepts images on a *user* message, so if the conversation
    ends on an assistant turn (or is empty) we open a new one.
    """
    parts = [_image_part(ref) for ref in images]
    if turns and turns[-1].get("role") == "user":
        last = turns[-1]
        text = last.get("content") if isinstance(last.get("content"), str) else ""
    else:
        last = {"role": "user", "content": ""}
        turns.append(last)
        text = ""
    # An empty text block is rejected outright, so only include one when there
    # is something to say.
    last["content"] = ([{"type": "text", "text": text}] if text else []) + parts


def text_inference(
    messages: list[dict],
    images: Optional[list[str]] = None,
    *,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: float = 90.0,
) -> str:
    """Run one textInference task and return the generated text.

    `images` may hold https URLs (e.g. a Linq-hosted screenshot), data URIs, or
    raw base64. Every form is downloaded/decoded, downscaled, and inlined as an
    Anthropic image content part — Runware rejects both a top-level `images` key
    and `source.type="url"`.
    """
    if not API_KEY:
        raise RunwareError("RUNWARE_API_KEY not set — cannot call Runware")

    # Two shape rules the task API enforces, handled here so callers can keep
    # writing ordinary OpenAI-style message lists:
    #   1. messages[].role accepts only user / assistant / tool. A "system"
    #      message must be lifted into settings.systemPrompt or the request is
    #      rejected with invalidMessageRole.
    #   2. maxTokens and temperature live under settings. At the top level they
    #      come back as unsupportedParameter.
    system_prompt = "\n\n".join(
        m["content"] for m in messages if m.get("role") == "system"
    )
    # Shallow-copy each turn: _attach_images rewrites `content` in place, and the
    # caller's message dicts must not change under them.
    turns = [dict(m) for m in messages if m.get("role") != "system"]

    settings: dict = {"maxTokens": max_tokens, "temperature": temperature}
    if system_prompt:
        settings["systemPrompt"] = system_prompt

    if images:
        _attach_images(turns, images)

    task: dict = {
        "taskType": "textInference",
        "taskUUID": str(uuid.uuid4()),
        "model": model or MODEL,
        "messages": turns,
        "settings": settings,
    }

    try:
        resp = httpx.post(
            BASE_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=[task],
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise RunwareError(f"Runware request failed: {e}") from e

    try:
        body = resp.json()
    except ValueError:
        raise RunwareError(f"Runware HTTP {resp.status_code}: {resp.text[:400]}")

    if resp.status_code >= 400 or "errors" in body:
        errs = body.get("errors") if isinstance(body, dict) else body
        raise RunwareError(f"Runware HTTP {resp.status_code}: {errs}")

    data = body.get("data") if isinstance(body, dict) else None
    if not data:
        raise RunwareError(f"Runware returned no data: {body}")

    text = data[0].get("text")
    if text is None:
        raise RunwareError(f"Runware task had no text: {data[0]}")
    return text


def list_models(query: str = "", limit: int = 40, timeout: float = 30.0) -> list[dict]:
    """Best-effort catalog dump (modelSearch task) to confirm exact AIR ids."""
    if not API_KEY:
        raise RunwareError("RUNWARE_API_KEY not set")
    task = {
        "taskType": "modelSearch",
        "taskUUID": str(uuid.uuid4()),
        "category": "llm",
        "search": query,
        "limit": limit,
    }
    resp = httpx.post(BASE_URL, headers={"Authorization": f"Bearer {API_KEY}"},
                      json=[task], timeout=timeout)
    body = resp.json()
    if resp.status_code >= 400 or "errors" in body:
        raise RunwareError(f"modelSearch failed: {body}")
    data = body.get("data") or []
    return data[0].get("results", data) if data else []
