"""Per-user negotiation storage.

A `Store` persists Deals and indexes them three ways:
  • by deal id            — direct lookup / card rendering
  • by user id            — "list my deals" (`phone:+1205…`)
  • by chat id / phone    — route an inbound Linq message to the right deal

It also holds two pieces of per-user conversation state that are not deals:
  • **focus**     — which deal an unqualified message applies to. Explicit and
                    sticky; a new listing link moves it, nothing else does.
  • **user meta** — `{last_card_kind, last_list, msg_times, onboarded}`.
                    `last_card_kind` is what makes a bare `1` a SWITCH rather
                    than a price, and `msg_times` backs the per-phone throttle.

Three backends, chosen by env at first use (see `get_store`):
  • RedisStore   — Upstash over REST. Only when both UPSTASH_* vars are set.
  • FileStore    — JSON on local disk under `CLOSER_STORE_PATH`. The event
                   default: the backend runs on a laptop, and a restart must not
                   lose the demo's deals.
  • MemoryStore  — no config; used by tests and `/simulate`.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import quote, unquote

import httpx

from app.state import Deal, DealState


class Store(Protocol):
    def get_deal(self, deal_id: str) -> Optional[Deal]: ...
    def save_deal(self, deal: Deal) -> None: ...
    def list_deals(self, user_id: str) -> list[Deal]: ...
    def delete_deal(self, deal_id: str) -> None: ...
    def find_by_chat(self, chat_id: str) -> Optional[Deal]: ...
    def find_active_by_phone(self, phone: str) -> Optional[Deal]: ...
    def list_pending_research(self) -> list[Deal]: ...

    # multi-deal focus + per-user conversation state
    def get_focus(self, user_id: str) -> Optional[str]: ...
    def set_focus(self, user_id: str, deal_id: str) -> None: ...
    def get_user_meta(self, user_id: str) -> dict: ...
    def set_user_meta(self, user_id: str, meta: dict) -> None: ...


def _sort_recent(deals: list[Deal]) -> list[Deal]:
    return sorted(deals, key=lambda d: d.updated_at, reverse=True)


class MemoryStore:
    def __init__(self) -> None:
        self._deals: dict[str, Deal] = {}
        self._focus: dict[str, str] = {}
        self._meta: dict[str, dict] = {}

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        return self._deals.get(deal_id)

    def save_deal(self, deal: Deal) -> None:
        deal.touch()
        # store a copy so callers mutating their reference don't alias the store
        self._deals[deal.id] = deal.model_copy(deep=True)

    def list_deals(self, user_id: str) -> list[Deal]:
        return _sort_recent([d for d in self._deals.values() if d.user_id == user_id])

    def delete_deal(self, deal_id: str) -> None:
        deal = self._deals.pop(deal_id, None)
        if deal and self._focus.get(deal.user_id) == deal_id:
            self._focus.pop(deal.user_id, None)

    def find_by_chat(self, chat_id: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.chat_id == chat_id]
        return _sort_recent(hits)[0] if hits else None

    def find_active_by_phone(self, phone: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.phone == phone and d.is_active()]
        return _sort_recent(hits)[0] if hits else None

    def list_pending_research(self) -> list[Deal]:
        return [d for d in self._deals.values() if d.state == DealState.AWAITING_RESEARCH]

    def get_focus(self, user_id: str) -> Optional[str]:
        return self._focus.get(user_id)

    def set_focus(self, user_id: str, deal_id: str) -> None:
        self._focus[user_id] = deal_id

    def get_user_meta(self, user_id: str) -> dict:
        # Deep copy: meta nests mutables (`msg_times` is a list), so a shallow
        # copy would let a caller mutate stored state by accident.
        return copy.deepcopy(self._meta.get(user_id) or {})

    def set_user_meta(self, user_id: str, meta: dict) -> None:
        self._meta[user_id] = copy.deepcopy(meta)


class FileStore:
    """JSON-per-deal on local disk, mirrored in memory.

    Reads are served from the mirror (loaded once on boot), so lookups cost what
    MemoryStore costs. Every write is atomic — a uniquely-named temp file in the
    same directory, then `os.replace` — so a crash or a concurrent writer can
    never leave a half-written deal on disk. A lock serialises mutations because
    research runs on a background thread while requests are still arriving.

    Layout::

        <root>/deals/<deal_id>.json
        <root>/users/<url-quoted user_id>.json   -> {"focus": ..., "meta": {...}}
    """

    def __init__(self, root: str | os.PathLike) -> None:
        self._root = Path(root)
        self._deals_dir = self._root / "deals"
        self._users_dir = self._root / "users"
        self._deals_dir.mkdir(parents=True, exist_ok=True)
        self._users_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._deals: dict[str, Deal] = {}
        self._focus: dict[str, str] = {}
        self._meta: dict[str, dict] = {}
        self._load()

    # ── disk ─────────────────────────────────────────────────────────────────
    def _load(self) -> None:
        for path in self._deals_dir.glob("*.json"):
            try:
                deal = Deal.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue          # a corrupt deal must not stop the app booting
            self._deals[deal.id] = deal
        for path in self._users_dir.glob("*.json"):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            user_id = unquote(path.stem)
            if blob.get("focus"):
                self._focus[user_id] = blob["focus"]
            if blob.get("meta"):
                self._meta[user_id] = blob["meta"]

    @staticmethod
    def _write_atomic(path: Path, payload: str) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)                  # atomic within a filesystem
        finally:
            tmp.unlink(missing_ok=True)

    def _user_path(self, user_id: str) -> Path:
        # `phone:+12055551234` contains ':' and '+'; quote so it is a legal
        # filename everywhere, and reversible on load.
        return self._users_dir / f"{quote(user_id, safe='')}.json"

    def _flush_user(self, user_id: str) -> None:
        blob = {"focus": self._focus.get(user_id), "meta": self._meta.get(user_id) or {}}
        self._write_atomic(self._user_path(user_id), json.dumps(blob))

    # ── deals ────────────────────────────────────────────────────────────────
    def get_deal(self, deal_id: str) -> Optional[Deal]:
        return self._deals.get(deal_id)

    def save_deal(self, deal: Deal) -> None:
        deal.touch()
        with self._lock:
            self._deals[deal.id] = deal.model_copy(deep=True)
            self._write_atomic(self._deals_dir / f"{deal.id}.json", deal.model_dump_json())

    def list_deals(self, user_id: str) -> list[Deal]:
        return _sort_recent([d for d in self._deals.values() if d.user_id == user_id])

    def delete_deal(self, deal_id: str) -> None:
        with self._lock:
            deal = self._deals.pop(deal_id, None)
            (self._deals_dir / f"{deal_id}.json").unlink(missing_ok=True)
            if deal and self._focus.get(deal.user_id) == deal_id:
                self._focus.pop(deal.user_id, None)
                self._flush_user(deal.user_id)

    def find_by_chat(self, chat_id: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.chat_id == chat_id]
        return _sort_recent(hits)[0] if hits else None

    def find_active_by_phone(self, phone: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.phone == phone and d.is_active()]
        return _sort_recent(hits)[0] if hits else None

    def list_pending_research(self) -> list[Deal]:
        return [d for d in self._deals.values() if d.state == DealState.AWAITING_RESEARCH]

    # ── per-user state ───────────────────────────────────────────────────────
    def get_focus(self, user_id: str) -> Optional[str]:
        return self._focus.get(user_id)

    def set_focus(self, user_id: str, deal_id: str) -> None:
        with self._lock:
            self._focus[user_id] = deal_id
            self._flush_user(user_id)

    def get_user_meta(self, user_id: str) -> dict:
        return copy.deepcopy(self._meta.get(user_id) or {})

    def set_user_meta(self, user_id: str, meta: dict) -> None:
        with self._lock:
            self._meta[user_id] = copy.deepcopy(meta)
            self._flush_user(user_id)


class RedisStore:
    """Upstash Redis via its REST API. Commands POST as a JSON array -> {"result": ...}."""

    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._h = {"Authorization": f"Bearer {token}"}

    def _cmd(self, *args) -> object:
        r = httpx.post(self._url, headers=self._h, json=list(args), timeout=15.0)
        r.raise_for_status()
        return r.json().get("result")

    def _pipeline(self, cmds: list[list]) -> list:
        r = httpx.post(f"{self._url}/pipeline", headers=self._h, json=cmds, timeout=15.0)
        r.raise_for_status()
        return [item.get("result") for item in r.json()]

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        raw = self._cmd("GET", f"deal:{deal_id}")
        return Deal.model_validate_json(raw) if raw else None

    def save_deal(self, deal: Deal) -> None:
        deal.touch()
        cmds: list[list] = [
            ["SET", f"deal:{deal.id}", deal.model_dump_json()],
            ["SADD", f"user:{deal.user_id}:deals", deal.id],
        ]
        if deal.chat_id:
            cmds.append(["SET", f"chat:{deal.chat_id}", deal.id])
        if deal.phone and deal.is_active():
            cmds.append(["SET", f"phone:{deal.phone}:active", deal.id])
        cmds.append(["SADD" if deal.state == DealState.AWAITING_RESEARCH else "SREM",
                     "pending:research", deal.id])
        self._pipeline(cmds)

    def list_deals(self, user_id: str) -> list[Deal]:
        ids = self._cmd("SMEMBERS", f"user:{user_id}:deals") or []
        if not ids:
            return []
        rows = self._pipeline([["GET", f"deal:{i}"] for i in ids])
        deals = [Deal.model_validate_json(r) for r in rows if r]
        return _sort_recent(deals)

    def delete_deal(self, deal_id: str) -> None:
        deal = self.get_deal(deal_id)
        if not deal:
            return
        cmds = [["DEL", f"deal:{deal_id}"],
                ["SREM", f"user:{deal.user_id}:deals", deal_id]]
        if deal.chat_id:
            cmds.append(["DEL", f"chat:{deal.chat_id}"])
        self._pipeline(cmds)
        if self.get_focus(deal.user_id) == deal_id:
            self._cmd("DEL", f"user:{deal.user_id}:focus")

    def find_by_chat(self, chat_id: str) -> Optional[Deal]:
        deal_id = self._cmd("GET", f"chat:{chat_id}")
        return self.get_deal(deal_id) if deal_id else None

    def find_active_by_phone(self, phone: str) -> Optional[Deal]:
        deal_id = self._cmd("GET", f"phone:{phone}:active")
        if not deal_id:
            return None
        deal = self.get_deal(deal_id)
        return deal if (deal and deal.is_active()) else None

    def list_pending_research(self) -> list[Deal]:
        ids = self._cmd("SMEMBERS", "pending:research") or []
        if not ids:
            return []
        rows = self._pipeline([["GET", f"deal:{i}"] for i in ids])
        deals = [Deal.model_validate_json(r) for r in rows if r]
        return [d for d in deals if d.state == DealState.AWAITING_RESEARCH]

    def get_focus(self, user_id: str) -> Optional[str]:
        return self._cmd("GET", f"user:{user_id}:focus") or None

    def set_focus(self, user_id: str, deal_id: str) -> None:
        self._cmd("SET", f"user:{user_id}:focus", deal_id)

    def get_user_meta(self, user_id: str) -> dict:
        raw = self._cmd("GET", f"user:{user_id}:meta")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}

    def set_user_meta(self, user_id: str, meta: dict) -> None:
        self._cmd("SET", f"user:{user_id}:meta", json.dumps(meta))


_store: Optional[Store] = None


def get_store() -> Store:
    """Upstash if configured → CLOSER_STORE_PATH if set → in-memory."""
    global _store
    if _store is None:
        url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
        path = os.getenv("CLOSER_STORE_PATH", "").strip()
        if url and token:
            _store = RedisStore(url, token)
        elif path:
            _store = FileStore(path)
        else:
            _store = MemoryStore()
    return _store


def set_store(store: Optional[Store]) -> None:
    """Swap the process-wide store. Tests use this; nothing else should."""
    global _store
    _store = store


def backend_name() -> str:
    return type(get_store()).__name__
