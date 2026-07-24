"""Dev 2 Phase 2 — the message surface.

Covers the parts of §5 that a unit test can actually pin down: the exact JSON
shapes we send to Partner API v3, the inbound reaction parse, the promise that
decorative calls never raise, the effect chosen for a state transition, and that
every card renders for every deal state including the null ones.

What these tests deliberately do NOT do is hit the network. The shapes here were
read off `@linqapp/sdk` 2.5.0 and the live webhook docs; the round trip itself is
verified by hand against the real number (LINQ.md §Phase 0 probe results).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import cards, linq, render
from app.state import Deal, DealState

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name: str) -> Deal:
    return Deal(**json.loads((FIXTURES / name).read_text()))


@pytest.fixture
def camry() -> Deal:
    return _fixture("deal_camry.json")


# ── effect payloads (§5.4) ───────────────────────────────────────────────────
def test_screen_and_bubble_effects_carry_the_right_type() -> None:
    """`type` must agree with `name` — a mismatch is a 400, not a plain send."""
    assert linq._effect_payload("confetti") == {"name": "confetti", "type": "screen"}
    assert linq._effect_payload("celebration") == {"name": "celebration", "type": "screen"}
    assert linq._effect_payload("fireworks") == {"name": "fireworks", "type": "screen"}
    assert linq._effect_payload("slam") == {"name": "slam", "type": "bubble"}


def test_unknown_effect_is_dropped_not_guessed() -> None:
    """An unknown name degrades to a plain send. Guessing the family would fail
    the whole message, and the message is the part that matters."""
    assert linq._effect_payload("glitter") is None
    assert linq._effect_payload("") is None
    assert linq._effect_payload(None) is None


def test_message_body_shapes() -> None:
    assert linq._message_body("hi") == {"parts": [{"type": "text", "value": "hi"}]}

    with_media = linq._message_body("your card", attachment_id="att_1")
    assert with_media["parts"] == [{"type": "text", "value": "your card"},
                                   {"type": "media", "attachment_id": "att_1"}]

    # A media part takes `url` OR `attachment_id`, never both.
    by_url = linq._message_body(None, media_url="https://cdn/x.png")
    assert by_url["parts"] == [{"type": "media", "url": "https://cdn/x.png"}]

    assert linq._message_body("closed", effect="confetti")["effect"] == \
        {"name": "confetti", "type": "screen"}


def test_message_body_refuses_to_send_nothing() -> None:
    with pytest.raises(linq.LinqError):
        linq._message_body(None)


# ── message ids (§5.2 needs these) ───────────────────────────────────────────
@pytest.mark.parametrize("response,expected", [
    ({"chat": {"message": {"id": "m1"}}}, "m1"),      # POST /v3/chats
    ({"message": {"id": "m2"}}, "m2"),                # POST /v3/chats/{id}/messages
    ({"id": "m3"}, "m3"),
    ({"chat": {"id": "c1"}}, None),                   # a chat id is not a message id
    ({}, None),
    (None, None),
])
def test_sent_message_id(response, expected) -> None:
    assert linq.sent_message_id(response) == expected


# ── decorative calls never raise (the C1 contract) ───────────────────────────
def test_react_and_typing_swallow_transport_failures(monkeypatch) -> None:
    """A tapback that 500s must not cost a negotiation turn."""
    def boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(linq, "_request", boom)
    assert linq.react("m1", "like")["ok"] is False
    assert linq.typing("c1", True)["ok"] is False
    assert linq.unreact("m1", "like")["ok"] is False


def test_decorative_calls_no_op_without_an_id() -> None:
    assert linq.react("", "like")["ok"] is False
    assert linq.react(None, "like")["ok"] is False
    assert linq.typing(None)["ok"] is False


def test_react_normalises_non_standard_types(monkeypatch) -> None:
    """Anything outside the six iMessage tapbacks has to ride as `custom`."""
    sent: dict = {}

    def capture(method, url, *, json=None, timeout=None):
        sent.update({"method": method, "url": url, "body": json})
        return {"status": "accepted"}

    monkeypatch.setattr(linq, "_request", capture)

    linq.react("m1", "like")
    assert sent["body"] == {"operation": "add", "type": "like"}
    assert sent["url"].endswith("/v3/messages/m1/reactions")

    linq.react("m1", "🔥")
    assert sent["body"] == {"operation": "add", "type": "custom", "custom_emoji": "🔥"}


def test_typing_while_clears_the_indicator_even_on_exception(monkeypatch) -> None:
    """The `finally` is the point: an exception mid-turn must not leave the
    thread showing us typing forever."""
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(linq, "typing", lambda chat_id, on=True: calls.append((chat_id, on)))

    with pytest.raises(ValueError):
        with linq.typing_while("c1"):
            raise ValueError("inference blew up")

    assert calls == [("c1", True), ("c1", False)]


def test_send_effect_retries_without_the_effect(monkeypatch) -> None:
    """The close message lands even if the effect is rejected."""
    attempts: list[dict] = []

    def fake_send(to, text=None, **kw):
        attempts.append(kw)
        if kw.get("effect"):
            raise linq.LinqError("400 unsupported effect")
        return {"chat": {"message": {"id": "m9"}}}

    monkeypatch.setattr(linq, "send", fake_send)
    assert linq.send_effect("+1205", "we closed", "confetti")["chat"]["message"]["id"] == "m9"
    assert [a.get("effect") for a in attempts] == ["confetti", None]


# ── inbound parsing ──────────────────────────────────────────────────────────
def test_parse_webhook_captures_the_message_id() -> None:
    """§5.1 reacts to the inbound message, so its id has to survive the parse."""
    inb = linq.parse_webhook({
        "event_type": "message.received",
        "data": {"chat": {"id": "c1"}, "id": "m1", "direction": "inbound",
                 "sender_handle": {"handle": "+12055550100"},
                 "parts": [{"type": "text", "value": "he said 5400"}]},
    })
    assert inb is not None
    assert (inb.chat_id, inb.message_id, inb.sender) == ("c1", "m1", "+12055550100")
    assert inb.text == "he said 5400"


def test_parse_reaction_reads_the_documented_shape() -> None:
    rx = linq.parse_reaction({
        "event_type": "reaction.added",
        "data": {"chat_id": "c1", "message_id": "m1", "reaction_type": "question",
                 "is_from_me": False, "from": "+12055550100",
                 "from_handle": {"handle": "+12055550100"}},
    })
    assert rx is not None
    assert (rx.chat_id, rx.message_id, rx.reaction) == ("c1", "m1", "question")
    assert rx.sender == "+12055550100"
    assert rx.removed is False


def test_parse_reaction_drops_our_own_echoes() -> None:
    """Our own ❗/❤️ tapbacks echo back with `is_from_me: true`. Without this
    guard every tapback we send re-enters as a user command and the agent talks
    to itself for as long as the thread is alive."""
    assert linq.parse_reaction({
        "event_type": "reaction.added",
        "data": {"chat_id": "c1", "message_id": "m1", "reaction_type": "like",
                 "is_from_me": True, "from": "+12052611117"},
    }) is None


def test_parse_reaction_marks_removals_and_ignores_other_events() -> None:
    rx = linq.parse_reaction({
        "event_type": "reaction.removed",
        "data": {"chat_id": "c1", "message_id": "m1", "reaction_type": "like",
                 "is_from_me": False, "from": "+1205"},
    })
    assert rx is not None and rx.removed is True

    assert linq.parse_reaction({"event_type": "message.received", "data": {}}) is None
    assert linq.parse_reaction({"event_type": "chat.typing_indicator.started"}) is None
    assert linq.parse_reaction(None) is None


def test_a_reaction_event_is_not_a_message() -> None:
    """Both parsers see every event, so each must reject the other's shape."""
    assert linq.parse_webhook({
        "event_type": "reaction.added",
        "data": {"chat_id": "c1", "message_id": "m1", "reaction_type": "like"},
    }) is None


# ── explanations (§7 B5) ─────────────────────────────────────────────────────
def test_explain_names_the_number_the_spread_and_the_odds(camry: Deal) -> None:
    text = cards.explain(camry)
    snap = camry.snapshot or {}
    assert f"${snap['offer']:,.0f}" in text
    assert f"${snap['floor_point_est']:,.0f}" in text
    assert f"{snap['p_accept']:.0%}" in text
    assert "±" in text
    assert "**" not in text            # §5.7: iMessage renders no markdown


def test_explain_quotes_the_bluff_turn_when_there_is_one(camry: Deal) -> None:
    found = cards.bluff_turn(camry, cards._trajectory(camry))
    assert found is not None, "the Camry fixture is the bluff fixture"
    assert f"Turn {found[0]['turn']}" in cards.explain(camry)


@pytest.mark.parametrize("state", [DealState.AWAITING_LINK,
                                   DealState.AWAITING_RESEARCH,
                                   DealState.NEGOTIATING])
def test_explain_degrades_without_a_snapshot(state: DealState) -> None:
    """A judge can say "why" in the first thirty seconds, before there is any
    math to show. That is a designed state, not an error."""
    deal = Deal(user_id="phone:+12055550100", title="2016 Honda Civic EX", state=state)
    text = cards.explain(deal)
    assert text and "None" not in text and "Traceback" not in text


def test_explain_never_apologises(camry: Deal) -> None:
    """B3 voice rule — never apologise, never say "I'm an AI"."""
    for deal in (camry, Deal(user_id="phone:+1", state=DealState.AWAITING_LINK)):
        low = cards.explain(deal).lower()
        assert "sorry" not in low
        assert "i'm an ai" not in low and "as an ai" not in low


# ── tapback replies (§5.2) ───────────────────────────────────────────────────
def test_softer_offer_copy_shows_what_the_softer_number_costs(camry: Deal) -> None:
    text = cards.softer_offer(camry, 5000.0, 0.62)
    assert "$5,000" in text and "62%" in text


def test_offer_locked_and_pinned_are_short(camry: Deal) -> None:
    assert "$" in cards.offer_locked(camry)
    assert cards._name(camry) in cards.pinned(camry)


# ── PNG cards (§4.6 / B4) ────────────────────────────────────────────────────
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("name", ["deal_camry.json", "deal_civic.json",
                                  "deal_f150.json", "deal_tacoma.json",
                                  "deal_fresh.json"])
def test_deal_png_renders_for_every_fixture_state(name: str) -> None:
    data = render.deal_png(_fixture(name))
    assert data.startswith(PNG_MAGIC)
    assert len(data) > 5_000


def test_deal_png_survives_an_empty_deal() -> None:
    """Never raises — the chart is decoration on a message that must arrive."""
    data = render.deal_png(Deal(user_id="phone:+12055550100"))
    assert data.startswith(PNG_MAGIC)


def test_deal_png_survives_a_corrupt_snapshot(camry: Deal) -> None:
    camry.snapshot = {"offer": "not a number", "p_accept": object()}
    assert render.deal_png(camry).startswith(PNG_MAGIC)


def test_stats_png_renders_populated_and_empty() -> None:
    deals = [_fixture(n) for n in ("deal_camry.json", "deal_f150.json",
                                   "deal_tacoma.json")]
    assert render.stats_png(deals).startswith(PNG_MAGIC)
    assert render.stats_png([]).startswith(PNG_MAGIC)


def test_render_reads_the_bluff_conjunction_from_cards(camry: Deal) -> None:
    """The PNG callout and the Unicode card must never disagree about whether a
    bluff happened — so there is one implementation and `render` imports it."""
    assert render.cards.bluff_turn is cards.bluff_turn


# ── main.py wiring (§5.1, §5.2, §5.4) ────────────────────────────────────────
from app import main                                          # noqa: E402
from app.store import MemoryStore                             # noqa: E402

PHONE = "+12055551234"
USER = "phone:+12055551234"


@pytest.fixture
def store(monkeypatch):
    """A clean in-memory store wired into main for the duration of a test."""
    fresh = MemoryStore()
    monkeypatch.setattr(main, "STORE", fresh)
    return fresh


def _closed(store, *, title: str, offer: float) -> Deal:
    deal = Deal(user_id=USER, phone=PHONE, title=title, asking=offer + 1000,
                last_user_offer=offer, closed_price=offer, state=DealState.CLOSED)
    store.save_deal(deal)
    return deal


class TestOutcomeEffect:
    """§5.4 — three effects, chosen from the transition this turn made."""

    def test_first_ever_close_gets_celebration(self, store) -> None:
        deal = Deal(user_id=USER, phone=PHONE, state=DealState.CLOSED)
        store.save_deal(deal)
        assert main._outcome_effect(deal, DealState.NEGOTIATING) == "celebration"

    def test_a_later_close_gets_confetti(self, store) -> None:
        _closed(store, title="2014 Ford F-150 XLT", offer=18_000)
        deal = Deal(user_id=USER, phone=PHONE, state=DealState.CLOSED)
        store.save_deal(deal)
        assert main._outcome_effect(deal, DealState.NEGOTIATING) == "confetti"

    def test_walk_gets_slam(self, store) -> None:
        deal = Deal(user_id=USER, phone=PHONE, state=DealState.WALKED)
        store.save_deal(deal)
        assert main._outcome_effect(deal, DealState.NEGOTIATING) == "slam"

    def test_no_transition_fires_nothing(self, store) -> None:
        """A second "we have a deal" on an already-closed deal must not fire
        confetti again — the effect belongs to the moment, not the state."""
        deal = Deal(user_id=USER, phone=PHONE, state=DealState.CLOSED)
        store.save_deal(deal)
        assert main._outcome_effect(deal, DealState.CLOSED) is None
        live = Deal(user_id=USER, phone=PHONE, state=DealState.NEGOTIATING)
        assert main._outcome_effect(live, DealState.NEGOTIATING) is None


class TestSofterOffer:
    """§5.2 — 👎 moves the number one visible notch, priced off the posterior."""

    def test_moves_a_quarter_of_the_way_to_their_price(self, camry: Deal) -> None:
        offer = (camry.snapshot or {})["offer"]
        result = main._softer(camry)
        assert result is not None
        softer, p_accept = result
        expected = offer + main.SOFTER_NOTCH * (camry.last_seller_price - offer)
        assert softer == pytest.approx(expected, abs=0.01)
        assert softer > offer                    # softer means better for them
        assert p_accept is not None and p_accept > (camry.snapshot or {})["p_accept"]

    def test_no_snapshot_means_nothing_to_soften(self) -> None:
        assert main._softer(Deal(user_id=USER)) is None

    def test_refuses_to_bid_above_their_own_price(self) -> None:
        """If we are already at or above what they are asking, there is no
        softer number — there is a deal."""
        deal = Deal(user_id=USER, asking=6400, last_seller_price=5000,
                    snapshot={"offer": 5200.0})
        assert main._softer(deal) is None


class TestReactionRouting:
    """§5.2 — a tapback on our message is a first-class command."""

    def _spy(self, monkeypatch) -> list[tuple[str, str]]:
        sent: list[tuple[str, str]] = []
        monkeypatch.setattr(main, "_send_now",
                            lambda phone, msg: sent.append((phone, msg)))
        return sent

    def _rx(self, kind: str) -> linq.InboundReaction:
        return linq.InboundReaction(chat_id="c1", sender=PHONE,
                                    message_id="m1", reaction=kind)

    def test_question_explains_the_math_with_the_chart(self, store, monkeypatch,
                                                       camry) -> None:
        """❓ answers in prose AND in the picture — the flat stretch in the
        curve is the argument, so the explanation carries the same PNG."""
        delivered: list[tuple] = []
        monkeypatch.setattr(main, "_deliver",
                            lambda phone, msg, *, effect, image:
                            delivered.append((phone, msg, effect, image)))
        camry.user_id, camry.phone = USER, PHONE
        store.save_deal(camry)
        store.set_focus(USER, camry.id)

        main._process_reaction(self._rx("question"))

        assert len(delivered) == 1
        phone, msg, effect, image = delivered[0]
        assert phone == PHONE and "Why" in msg and effect is None
        assert image is not None and image[0].startswith(PNG_MAGIC)

    def test_like_confirms_the_offer_is_out(self, store, monkeypatch, camry) -> None:
        camry.user_id, camry.phone = USER, PHONE
        store.save_deal(camry)
        store.set_focus(USER, camry.id)
        sent = self._spy(monkeypatch)
        main._process_reaction(self._rx("like"))
        assert "👍" in sent[0][1]

    def test_dislike_persists_the_softer_number(self, store, monkeypatch, camry) -> None:
        camry.user_id, camry.phone = USER, PHONE
        store.save_deal(camry)
        store.set_focus(USER, camry.id)
        before = (camry.snapshot or {})["offer"]
        sent = self._spy(monkeypatch)
        main._process_reaction(self._rx("dislike"))
        fresh = store.get_deal(camry.id)
        assert fresh.last_user_offer > before
        assert fresh.snapshot["offer"] == fresh.last_user_offer
        assert "Send" in sent[0][1]

    def test_emphasize_pins_the_deal(self, store, monkeypatch, camry) -> None:
        camry.user_id, camry.phone = USER, PHONE
        store.save_deal(camry)
        other = Deal(user_id=USER, phone=PHONE, title="2016 Honda Civic EX")
        store.save_deal(other)
        store.set_focus(USER, camry.id)
        sent = self._spy(monkeypatch)
        main._process_reaction(self._rx("emphasize"))
        assert store.get_focus(USER) == camry.id
        assert "📌" in sent[0][1]

    def test_a_tapback_from_a_stranger_is_a_no_op(self, store, monkeypatch) -> None:
        """No deals means nothing to act on — and never a crash on a worker
        thread, which the user would read as the tapback silently failing."""
        sent = self._spy(monkeypatch)
        main._process_reaction(self._rx("question"))
        assert sent == []


class TestInboundAcknowledgement:
    """§5.1 — the only tapbacks we send are the ones that mean something."""

    def test_an_ordinary_inbound_gets_no_tapback(self, store, monkeypatch) -> None:
        """No blanket 👍 read receipt. The typing indicator carries "we got it";
        a tapback on every message would drown ❗ and ❤️, which are the two that
        say something the user could not already see."""
        order: list[str] = []
        monkeypatch.setattr(linq, "react",
                            lambda mid, kind, emoji=None: order.append(f"react:{kind}"))
        monkeypatch.setattr(linq, "typing", lambda chat_id, on=True: None)
        monkeypatch.setattr(main, "route_message",
                            lambda *a, **k: order.append("inference") or "ok")
        main._process_inbound(linq.InboundMessage(
            chat_id="c1", message_id="m1", sender=PHONE, text="hey"))
        assert order == ["inference"]

    def test_a_bluff_turn_gets_an_emphasize_tapback(self, store, camry, monkeypatch) -> None:
        reacts: list[str] = []
        monkeypatch.setattr(linq, "react",
                            lambda mid, kind, emoji=None: reacts.append(kind))
        camry.user_id, camry.phone = USER, PHONE
        camry.signals_log = [{"bluff_claim": True}]
        main._signal_reaction(
            linq.InboundMessage(message_id="m1", sender=PHONE), camry)
        assert reacts == ["emphasize"]

    def test_the_closing_message_gets_a_heart(self, store, camry, monkeypatch) -> None:
        reacts: list[str] = []
        monkeypatch.setattr(linq, "react",
                            lambda mid, kind, emoji=None: reacts.append(kind))
        camry.state = DealState.CLOSED
        main._signal_reaction(
            linq.InboundMessage(message_id="m1", sender=PHONE), camry)
        assert reacts == ["love"]


class TestPngDelivery:
    """§5.5 — the chart rides along, and never costs the reply."""

    def test_card_and_stats_get_a_png(self, store, camry) -> None:
        camry.user_id, camry.phone = USER, PHONE
        store.save_deal(camry)
        image = main._card_image(camry, "deal")
        assert image is not None and image[0].startswith(PNG_MAGIC)
        assert image[1].endswith(".png")

        stats = main._card_image(camry, "stats")
        assert stats is not None and stats[0].startswith(PNG_MAGIC)

    def test_other_replies_get_no_image(self, store, camry) -> None:
        """A list, a help card or a rename has no chart to draw."""
        for kind in ("list", "help", "explain", None):
            assert main._card_image(camry, kind) is None

    def test_kill_switch_disables_rendering(self, store, camry, monkeypatch) -> None:
        monkeypatch.setattr(main, "PNG_CARDS", False)
        assert main._card_image(camry, "deal") is None

    def test_a_render_failure_costs_nothing(self, store, camry, monkeypatch) -> None:
        monkeypatch.setattr(main.render, "deal_png",
                            lambda d: (_ for _ in ()).throw(RuntimeError("no fonts")))
        assert main._card_image(camry, "deal") is None

    def test_delivery_falls_back_to_text_when_the_upload_fails(self, monkeypatch) -> None:
        """The text is the deliverable. A CDN hiccup must not cost the number."""
        plain: list[str] = []
        monkeypatch.setattr(linq, "send_media_bytes",
                            lambda *a, **k: (_ for _ in ()).throw(
                                linq.LinqError("503 from S3")))
        monkeypatch.setattr(linq, "send", lambda to, text=None, **k: plain.append(text))

        main._deliver(PHONE, "here is your card", effect=None,
                      image=(b"\x89PNG not really", "deal-card.png"))
        assert plain == ["here is your card"]

    def test_delivery_keeps_the_effect_on_the_media_send(self, monkeypatch) -> None:
        """Closing on a `card` reply must still fire confetti."""
        calls: list[dict] = []
        monkeypatch.setattr(linq, "send_media_bytes",
                            lambda to, text, data, fn, **k: calls.append(k))
        main._deliver(PHONE, "closed", effect="confetti",
                      image=(b"png", "deal-card.png"))
        assert calls == [{"effect": "confetti"}]

    def test_plain_replies_still_send_without_an_image(self, monkeypatch) -> None:
        sent: list[tuple[str, str]] = []
        monkeypatch.setattr(linq, "send_effect",
                            lambda to, text, fx: sent.append((text, fx)))
        main._deliver(PHONE, "we closed", effect="confetti", image=None)
        assert sent == [("we closed", "confetti")]
