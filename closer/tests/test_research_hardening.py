"""A4 — research hardening.

Three failure modes that each end a live demo quietly:
  • the listing 403s and we emit V=0/R=0, leaving a deal that can never build a
    belief and never says why;
  • six legal-but-slow steps stall the thread for two minutes;
  • a naked client gets blocked where a browser UA would not.
"""

from __future__ import annotations

import time

import pytest

from app import research

LINK = "https://www.cars.com/vehicledetail/blocked/"


def _fetch_result(text: str = "", error: str = "") -> dict:
    return {"text": text, "error": error, "url": LINK}


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setattr(research, "RESEARCH_MODE", "live")


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(research.runware, "available", lambda: False)


# ==========================================================================
# The 403 fallback — ask, don't guess
# ==========================================================================


class TestBlockedListing:
    def test_unreadable_listing_with_no_asking_is_marked_blocked(
            self, live_mode, no_llm, monkeypatch):
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(error="HTTP 403"))
        payload = research.run_research(LINK)
        assert payload["blocked"] is True
        assert "403" in payload["blocked_reason"]

    def test_blocked_payload_never_pretends_to_have_a_valuation(
            self, live_mode, no_llm, monkeypatch):
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(error="HTTP 403"))
        payload = research.run_research(LINK)
        val = research.to_valuation(payload)
        assert val["V"] == 0 and val["asking"] == 0
        # ...and the reason is in the payload, so the coach can say it out loud.
        assert "asking price" in payload["reasoning"]

    def test_a_known_asking_price_skips_the_blocked_path(
            self, live_mode, no_llm, monkeypatch):
        """The buyer already told us the price — a 403 is survivable."""
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(error="HTTP 403"))
        payload = research.run_research(LINK, asking=6_400)
        assert not payload.get("blocked")
        assert payload["fair_value"] > 0

    def test_a_readable_listing_is_never_blocked(self, live_mode, no_llm, monkeypatch):
        monkeypatch.setattr(
            research, "fetch_page",
            lambda url, **kw: _fetch_result(text="2008 Toyota Camry LE $6,400 128,000 miles"))
        payload = research.run_research(LINK)
        assert not payload.get("blocked")
        assert payload["facts"]["asking"] == 6_400

    def test_blocked_marker_survives_normalization(self):
        raw = research._blocked_payload(LINK, "HTTP 403")
        out = research._normalize(raw, LINK, None, [])
        assert out["blocked"] is True

    def test_blocked_run_records_a_step_for_the_trace(
            self, live_mode, no_llm, monkeypatch):
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(error="HTTP 403"))
        payload = research.run_research(LINK)
        assert any(s["tool"] == "blocked" for s in payload["steps"])

    def test_blocked_run_does_not_call_the_model(self, live_mode, monkeypatch):
        """Nothing to reason about — don't burn a Runware call or 40 seconds."""
        calls = []
        monkeypatch.setattr(research.runware, "available", lambda: True)
        monkeypatch.setattr(research.runware, "text_inference",
                            lambda *a, **kw: calls.append(1) or "{}")
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(error="HTTP 403"))
        research.run_research(LINK)
        assert calls == []


# ==========================================================================
# recompute_with_asking — the recovery once the user answers
# ==========================================================================


class TestRecomputeWithAsking:
    def test_an_asking_price_produces_a_real_valuation(self):
        blocked = research._blocked_payload(LINK, "HTTP 403")
        fixed = research.recompute_with_asking(blocked, 6_400)
        val = research.to_valuation(fixed)
        assert fixed["blocked"] is False
        assert val["asking"] == 6_400
        assert 0 < val["V"] < 6_400
        assert val["R"] > 0

    def test_the_valuation_is_the_conservative_haircut(self):
        fixed = research.recompute_with_asking(research._blocked_payload(LINK, ""), 10_000)
        assert fixed["fair_value"] == pytest.approx(8_900)

    def test_confidence_stays_low_without_comps(self):
        fixed = research.recompute_with_asking(research._blocked_payload(LINK, ""), 6_400)
        assert fixed["confidence"] == "low"
        assert fixed["red_flags"]                      # says why, doesn't stay silent

    def test_the_reasoning_names_the_price_the_user_gave(self):
        fixed = research.recompute_with_asking(research._blocked_payload(LINK, ""), 6_400)
        assert "6,400" in fixed["reasoning"]

    @pytest.mark.parametrize("bad", [0, -1, None])
    def test_a_useless_answer_leaves_the_deal_blocked(self, bad):
        blocked = research._blocked_payload(LINK, "")
        assert research.recompute_with_asking(blocked, bad)["blocked"] is True

    def test_the_original_payload_is_not_mutated(self):
        blocked = research._blocked_payload(LINK, "")
        research.recompute_with_asking(blocked, 6_400)
        assert blocked["blocked"] is True and blocked["fair_value"] == 0.0

    def test_result_survives_normalization_as_a_normal_payload(self):
        fixed = research.recompute_with_asking(research._blocked_payload(LINK, ""), 6_400)
        out = research._normalize(fixed, LINK, 6_400, [])
        assert "blocked" not in out                    # flag cleared, grammar normal
        assert out["fair_value"] > 0


# ==========================================================================
# The wall-clock cap
# ==========================================================================


class TestWallClock:
    def test_a_slow_agent_is_cut_off_instead_of_stalling_the_thread(
            self, live_mode, monkeypatch):
        monkeypatch.setattr(research, "RESEARCH_WALL_S", 0.25)
        monkeypatch.setattr(research, "RESEARCH_MAX_STEPS", 50)
        monkeypatch.setattr(research.runware, "available", lambda: True)
        monkeypatch.setattr(
            research, "fetch_page",
            lambda url, **kw: _fetch_result(text="2008 Camry $6,400"))

        calls = {"n": 0}

        def slow_model(*a, **kw):
            calls["n"] += 1
            time.sleep(0.1)
            return '{"tool": "web_search", "query": "camry comps"}'

        monkeypatch.setattr(research.runware, "text_inference", slow_model)
        monkeypatch.setattr(research, "web_search",
                            lambda q, **kw: {"results": [], "error": ""})

        started = time.monotonic()
        payload = research.run_research(LINK)
        elapsed = time.monotonic() - started

        assert elapsed < 3.0                    # nowhere near 50 steps
        assert calls["n"] < 50
        assert any(s["tool"] == "timeout" for s in payload["steps"])

    def test_the_cap_still_returns_a_usable_valuation(self, live_mode, monkeypatch):
        monkeypatch.setattr(research, "RESEARCH_WALL_S", 0.01)
        monkeypatch.setattr(research.runware, "available", lambda: True)
        monkeypatch.setattr(research.runware, "text_inference",
                            lambda *a, **kw: '{"tool": "web_search", "query": "x"}')
        monkeypatch.setattr(
            research, "fetch_page",
            lambda url, **kw: _fetch_result(text="2008 Toyota Camry LE $6,400"))
        payload = research.run_research(LINK)
        assert research.to_valuation(payload)["V"] > 0   # heuristic, not a crash

    def test_only_one_timeout_step_is_recorded(self, live_mode, monkeypatch):
        monkeypatch.setattr(research, "RESEARCH_WALL_S", 0.01)
        monkeypatch.setattr(research.runware, "available", lambda: True)
        monkeypatch.setattr(research.runware, "text_inference",
                            lambda *a, **kw: '{"tool": "web_search", "query": "x"}')
        monkeypatch.setattr(research, "fetch_page",
                            lambda url, **kw: _fetch_result(text="$6,400"))
        payload = research.run_research(LINK)
        assert sum(1 for s in payload["steps"] if s["tool"] == "timeout") == 1

    def test_a_fast_agent_is_not_cut_off(self, live_mode, monkeypatch):
        monkeypatch.setattr(research, "RESEARCH_WALL_S", 30.0)
        monkeypatch.setattr(research.runware, "available", lambda: True)
        monkeypatch.setattr(
            research, "fetch_page",
            lambda url, **kw: _fetch_result(text="2008 Toyota Camry LE $6,400"))
        monkeypatch.setattr(
            research.runware, "text_inference",
            lambda *a, **kw: '{"tool": "finish", "fair_value": 4200, "confidence": "med",'
                             ' "facts": {"asking": 6400}, "sources":'
                             ' [{"url": "https://kbb.com/x", "title": "KBB"}]}')
        payload = research.run_research(LINK)
        assert payload["fair_value"] == 4_200
        assert not any(s["tool"] == "timeout" for s in payload["steps"])


# ==========================================================================
# Browser identity on fetch_page
# ==========================================================================


class TestUserAgent:
    def test_fetch_page_presents_a_browser_user_agent(self, monkeypatch):
        """Some 403s are naked-client blocks, not real refusals."""
        seen: dict = {}

        class Resp:
            status_code, is_redirect, headers = 200, False, {"content-type": "text/html"}
            text = "<html><body>2008 Camry $6,400</body></html>"

        def fake_get(url, **kw):
            seen.update(kw.get("headers") or {})
            return Resp()

        monkeypatch.setattr(research.httpx, "get", fake_get)
        research.fetch_page("https://example.com/listing")
        assert "Mozilla/5.0" in seen.get("User-Agent", "")

    def test_the_wall_cap_is_configurable_from_env(self):
        assert research.RESEARCH_WALL_S > 0
