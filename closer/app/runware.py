"""Runware native task API client (text + vision), over httpx.

Runware speaks a single endpoint that takes a JSON ARRAY of task objects:

    POST https://api.runware.ai/v1
    Authorization: Bearer $RUNWARE_API_KEY
    [ { "taskType": "textInference", "taskUUID": "...", "model": "...",
        "messages": [ {"role": "user", "content": "..."} ],
        "images": ["<url|dataURI|uuid>"]   # optional, for vision
      } ]
    -> { "data": [ { "taskType": "textInference", "taskUUID": "...",
                     "text": "...", "finishReason": "stop", "cost": 0.0005 } ] }

One AIR model id (`anthropic:claude@sonnet-4.6`) does BOTH text and image->text,
so the same call powers classify / draft / screenshot extraction. We deliberately
use the native task API rather than the OpenAI /v1/chat/completions shim, because
the shim is text-only (no image inputs).
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import httpx

BASE_URL = os.getenv("RUNWARE_BASE_URL", "https://api.runware.ai/v1").rstrip("/")
API_KEY = os.getenv("RUNWARE_API_KEY", "").strip()
MODEL = os.getenv("RUNWARE_MODEL", "anthropic:claude@sonnet-4.6").strip()


class RunwareError(RuntimeError):
    """Any non-success from the Runware API (HTTP error or task-level error)."""


def available() -> bool:
    """True when a key is configured — gates the LLM path vs the rules fallback."""
    return bool(API_KEY)


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

    `images` may hold URLs (e.g. a Linq-hosted screenshot), data URIs, base64, or
    Runware image UUIDs — passed straight through for vision.
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
    turns = [m for m in messages if m.get("role") != "system"]

    settings: dict = {"maxTokens": max_tokens, "temperature": temperature}
    if system_prompt:
        settings["systemPrompt"] = system_prompt

    task: dict = {
        "taskType": "textInference",
        "taskUUID": str(uuid.uuid4()),
        "model": model or MODEL,
        "messages": turns,
        "settings": settings,
    }
    if images:
        task["images"] = images

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
