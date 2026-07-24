"""Phase 4 — agentic research tests.

The loop is exercised with a scripted fake model and fake tools: no network, no
API key, deterministic. What we assert is the contract the rest of the app leans
on — the payload shape, the sanity clamps, the derived R/V, and the fact that
every failure mode still yields a usable valuation instead of an exception.
"""

from __future__ import annotations

import json
import socket

import pytest

from app import research, runware


# ── HTML -> text ─────────────────────────────────────────────────────────────
def test_html_to_text_strips_markup_and_scripts():
    html = """
    <html><head><style>.a{color:red}</style></head>
    <body><script>var x = "not text";</script>
    <h1>2019 Mazda CX-5 Touring AWD</h1>
    <p>$16,000 &middot; 68,000 miles</p></body></html>
    """
    text = research.html_to_text(html)
    assert "2019 Mazda CX-5 Touring AWD" in text
    assert "68,000 miles" in text
    assert "not text" not in text and "color:red" not in text


def test_html_to_text_respects_cap():
    assert len(research.html_to_text("<p>" + "x" * 5000 + "</p>", cap=100)) == 100


# ── search result parsing ────────────────────────────────────────────────────
def test_ddg_redirect_links_are_unwrapped():
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.kbb.com%2Fmazda%2Fcx-5%2F2019%2F&rut=abc"
    assert research._unwrap_ddg(href) == "https://www.kbb.com/mazda/cx-5/2019/"


def test_ddg_sponsored_rows_are_dropped():
    assert research._is_ad("https://duckduckgo.com/y.js?ad_domain=cargurus.com")
    assert not research._is_ad("https://www.kbb.com/mazda/cx-5/2019/")


def test_web_search_never_raises_when_provider_dies(monkeypatch):
    monkeypatch.setattr(research, "_search_ddg",
                        lambda q, n: (_ for _ in ()).throw(RuntimeError("429 rate limited")))
    out = research.web_search("2019 mazda cx-5 value")
    assert out["results"] == [] and "unavailable" in out["error"]


def test_fetch_page_rejects_non_http():
    out = research.fetch_page("file:///etc/passwd")
    assert out["text"] == "" and out["error"] == "not an http(s) url"


# ── SSRF guard ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("addr", [
    "127.0.0.1",              # loopback
    "169.254.169.254",        # cloud metadata — the one that leaks credentials
    "10.0.0.5",               # private
    "172.16.4.4",             # private
    "192.168.1.1",            # private
    "0.0.0.0",                # unspecified
    "::1",                    # ipv6 loopback
    "fd00::1",                # ipv6 unique-local
    "::ffff:169.254.169.254",  # ipv4-mapped ipv6 metadata
    "100.64.0.1",             # CGNAT
    "224.0.0.1",              # multicast
    "not-an-ip",
])
def test_internal_addresses_are_blocked(addr):
    assert research._ip_is_blocked(addr)


@pytest.mark.parametrize("addr", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1::1"])
def test_public_addresses_are_allowed(addr):
    assert not research._ip_is_blocked(addr)


def _dns(monkeypatch, ip: str, *, only: str | None = None):
    """Resolve hostnames to `ip`. With `only`, other hosts resolve to themselves,
    so a redirect to a literal internal IP is still checked for real."""
    def fake(h, p, **kw):
        addr = ip if (only is None or h == only) else h
        fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (addr, p))]

    monkeypatch.setattr(research.socket, "getaddrinfo", fake)


def test_hostname_resolving_to_metadata_ip_is_rejected(monkeypatch):
    """The classic bypass: a public-looking name with an internal A record."""
    _dns(monkeypatch, "169.254.169.254")
    out = research.fetch_page("https://totally-legit-listings.com/car")
    assert out["text"] == "" and "blocked host" in out["error"]


def test_credentials_in_url_rejected():
    assert "credentials" in research._validate_url("https://user:pw@example.com/") or ""


def test_nonstandard_port_rejected(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    assert research._validate_url("http://example.com:6379/") == "port 6379 not allowed"


def test_trailing_dot_host_is_normalized(monkeypatch):
    seen = {}

    def fake_getaddrinfo(h, p, **kw):
        seen["host"] = h
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))]

    monkeypatch.setattr(research.socket, "getaddrinfo", fake_getaddrinfo)
    assert research._validate_url("https://EXAMPLE.com./x") is None
    assert seen["host"] == "example.com"


def test_redirect_to_internal_host_is_blocked(monkeypatch):
    """httpx's own follow_redirects would have walked straight into this."""
    _dns(monkeypatch, "93.184.216.34", only="public-site.com")
    hops = {"n": 0}

    class Resp:
        def __init__(self, redirect):
            self.is_redirect = redirect
            self.status_code = 302 if redirect else 200
            self.headers = ({"location": "http://169.254.169.254/latest/meta-data/"}
                            if redirect else {"content-type": "text/html"})
            self.text = "<p>ok</p>"

    def fake_get(url, **kw):
        hops["n"] += 1
        if hops["n"] == 1:
            return Resp(True)
        return Resp(False)

    monkeypatch.setattr(research.httpx, "get", fake_get)
    out = research.fetch_page("https://public-site.com/listing")
    assert out["text"] == "" and "blocked host" in out["error"]
    assert hops["n"] == 1                       # never issued the second request


def test_redirect_loop_terminates(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")

    class Resp:
        is_redirect = True
        status_code = 302
        headers = {"location": "https://public-site.com/again"}

    monkeypatch.setattr(research.httpx, "get", lambda url, **kw: Resp())
    out = research.fetch_page("https://public-site.com/listing")
    assert "too many redirects" in out["error"]


def test_dev_escape_hatch_allows_localhost(monkeypatch):
    monkeypatch.setattr(research, "ALLOW_PRIVATE_HOSTS", True)
    assert research._validate_url("http://127.0.0.1:8000/fixture.html") is None


# ── the loop ─────────────────────────────────────────────────────────────────
LISTING = "<h1>2019 Mazda CX-5 Touring AWD</h1><p>$16,000 - 68,000 miles - as is</p>"

FINISH = {
    "thought": "enough evidence",
    "tool": "finish",
    "fair_value": 14200,
    "hidden_costs": [{"item": "timing belt service due", "cost": 1200}],
    "red_flags": ["no service records"],
    "facts": {"year": 2019, "make": "Mazda", "model": "CX-5",
              "trim": "Touring AWD", "miles": 68000, "asking": 16000},
    "confidence": "high",
    "sources": [{"title": "KBB", "url": "https://kbb.com/x", "note": "$13.4k-$14.6k"}],
    "reasoning": "Comps cluster below asking and a belt service is due.",
}


@pytest.fixture
def wired(monkeypatch):
    """Force the LLM path on, stub the network, script the model's turns."""
    monkeypatch.setattr(runware, "available", lambda: True)
    monkeypatch.setattr(research, "RESEARCH_MODE", "live")
    monkeypatch.setattr(research, "fetch_page",
                        lambda url, cap=None: {"url": url,
                                               "text": research.html_to_text(LISTING),
                                               "error": None})
    monkeypatch.setattr(research, "web_search",
                        lambda q, n=5: {"query": q, "error": None, "results": [
                            {"title": "KBB CX-5", "url": "https://kbb.com/x",
                             "snippet": "private party $13,400-$14,600"}]})

    def script(turns: list[dict]):
        calls = {"n": 0}

        def fake(messages, images=None, **kw):
            i = min(calls["n"], len(turns) - 1)
            calls["n"] += 1
            return json.dumps(turns[i])

        monkeypatch.setattr(runware, "text_inference", fake)
        return calls

    return script


def test_loop_runs_tools_then_finishes(wired):
    wired([{"thought": "find comps", "tool": "web_search", "query": "2019 CX-5 value"},
           {"thought": "read it", "tool": "fetch_page", "url": "https://kbb.com/x"},
           FINISH])
    out = research.run_research("https://example.com/cx5", asking=16000)

    tools = [s["tool"] for s in out["steps"]]
    assert tools == ["fetch_page", "web_search", "fetch_page", "finish"]  # step 0 + 3 turns
    assert out["fair_value"] == 14200
    assert out["confidence"] == "high"
    assert out["sources"][0]["url"] == "https://kbb.com/x"
    assert out["listing_link"] == "https://example.com/cx5"


def test_valuation_derives_R_and_V(wired):
    wired([FINISH])
    out = research.run_research("https://example.com/cx5", asking=16000)
    v = research.to_valuation(out)
    assert v["V"] == 14200
    assert v["R"] == 13000                      # 14200 - 1200 hidden costs
    assert v["R"] > 0.65 * v["asking"]          # sanity floor not binding here


def test_absurd_fair_value_is_clamped(wired):
    wild = dict(FINISH, fair_value=999999)
    wired([wild])
    out = research.run_research("https://example.com/cx5", asking=16000)
    assert out["fair_value"] == pytest.approx(16000 * 1.05)


def test_hidden_costs_floor_R_at_65_percent_of_asking(wired):
    gutted = dict(FINISH, hidden_costs=[{"item": "engine", "cost": 9000}])
    wired([gutted])
    out = research.run_research("https://example.com/cx5", asking=16000)
    assert research.to_valuation(out)["R"] == pytest.approx(0.65 * 16000)


def test_uncited_high_confidence_is_downgraded(wired):
    wired([dict(FINISH, sources=[])])
    out = research.run_research("https://example.com/cx5", asking=16000)
    assert out["confidence"] == "med"


def test_bad_json_then_recovery(wired, monkeypatch):
    turns = [FINISH]
    calls = {"n": 0}

    def fake(messages, images=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return "I'll look into that for you!"     # not JSON
        return json.dumps(turns[0])

    monkeypatch.setattr(runware, "text_inference", fake)
    out = research.run_research("https://example.com/cx5", asking=16000)
    assert out["fair_value"] == 14200
    assert any(s["tool"] == "error" for s in out["steps"])


def test_step_budget_exhausted_falls_back(wired):
    wired([{"thought": "loop forever", "tool": "web_search", "query": "again"}])
    out = research.run_research("https://example.com/cx5", asking=16000, max_steps=3)
    assert out["confidence"] == "low"
    assert out["fair_value"] == pytest.approx(16000 * 0.89)
    assert any(s["tool"] == "timeout" for s in out["steps"])


def test_on_step_callback_streams_the_trace(wired):
    wired([{"thought": "comps", "tool": "web_search", "query": "q"}, FINISH])
    seen: list[dict] = []
    research.run_research("https://example.com/cx5", asking=16000, on_step=seen.append)
    assert [s["tool"] for s in seen] == ["fetch_page", "web_search", "finish"]


# ── offline / mock paths ─────────────────────────────────────────────────────
def test_offline_heuristic_when_no_api_key(monkeypatch):
    monkeypatch.setattr(runware, "available", lambda: False)
    monkeypatch.setattr(research, "RESEARCH_MODE", "live")
    monkeypatch.setattr(research, "fetch_page",
                        lambda url, cap=None: {"url": url,
                                               "text": research.html_to_text(LISTING),
                                               "error": None})
    out = research.run_research("https://example.com/cx5")
    assert out["fair_value"] == pytest.approx(16000 * 0.89)
    assert out["facts"]["year"] == 2019 and out["facts"]["miles"] == 68000
    assert "sold as-is, no warranty" in out["red_flags"]
    assert out["confidence"] == "low"


def test_dead_listing_page_still_returns_a_payload(monkeypatch):
    monkeypatch.setattr(runware, "available", lambda: False)
    monkeypatch.setattr(research, "RESEARCH_MODE", "live")
    monkeypatch.setattr(research, "fetch_page",
                        lambda url, cap=None: {"url": url, "text": "", "error": "HTTP 403"})
    out = research.run_research("https://example.com/cx5", asking=16000)
    assert out["fair_value"] == pytest.approx(16000 * 0.89)   # asking came from the caller
    assert out["steps"][0]["note"] == "HTTP 403"


def test_mock_mode_is_instant_and_shaped(monkeypatch):
    monkeypatch.setattr(research, "RESEARCH_MODE", "mock")
    out = research.run_research("https://example.com/cx5")
    v = research.to_valuation(out)
    assert (v["asking"], v["V"], v["R"]) == (16000, 14200, 13000)
    assert len(out["sources"]) == 3


def test_summary_message_has_the_numbers_and_receipts(monkeypatch):
    monkeypatch.setattr(research, "RESEARCH_MODE", "mock")
    msg = research.research_summary(research.run_research("https://example.com/cx5"))
    assert "$14,200" in msg and "$13,000" in msg
    assert "kbb.com" in msg
    assert "2019 Mazda CX-5 Touring AWD" in msg
