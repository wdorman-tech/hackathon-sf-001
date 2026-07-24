"""Per-user negotiation storage.

A `Store` persists Deals and indexes them three ways:
  • by deal id            — direct lookup / dashboard detail
  • by user id            — "list my deals" (Clerk user)
  • by chat id / phone    — route an inbound Linq message to the right deal

Two backends, chosen by env at import time:
  • MemoryStore  — default; zero setup; used locally and by the /simulate demo.
  • RedisStore   — Upstash Redis over REST (httpx, no driver). REQUIRED on Vercel,
                   where serverless functions don't share process memory. Activates
                   when UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN are set.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

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


def _sort_recent(deals: list[Deal]) -> list[Deal]:
    return sorted(deals, key=lambda d: d.updated_at, reverse=True)


class MemoryStore:
    def __init__(self) -> None:
        self._deals: dict[str, Deal] = {}

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        return self._deals.get(deal_id)

    def save_deal(self, deal: Deal) -> None:
        deal.touch()
        # store a copy so callers mutating their reference don't alias the store
        self._deals[deal.id] = deal.model_copy(deep=True)

    def list_deals(self, user_id: str) -> list[Deal]:
        return _sort_recent([d for d in self._deals.values() if d.user_id == user_id])

    def delete_deal(self, deal_id: str) -> None:
        self._deals.pop(deal_id, None)

    def find_by_chat(self, chat_id: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.chat_id == chat_id]
        return _sort_recent(hits)[0] if hits else None

    def find_active_by_phone(self, phone: str) -> Optional[Deal]:
        hits = [d for d in self._deals.values() if d.phone == phone and d.is_active()]
        return _sort_recent(hits)[0] if hits else None

    def list_pending_research(self) -> list[Deal]:
        return [d for d in self._deals.values() if d.state == DealState.AWAITING_RESEARCH]


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


_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is None:
        url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
        _store = RedisStore(url, token) if url and token else MemoryStore()
    return _store


def backend_name() -> str:
    return type(get_store()).__name__
