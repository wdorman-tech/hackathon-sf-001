"""A2/A3 — phone identity, multi-deal focus, and the persistent store.

The gate these are written against:
  two links from one phone produce two deals with focus on the second, and a
  backend restart loses nothing.
"""

from __future__ import annotations

import json

import pytest

from app import main
from app.state import Deal, DealState, normalize_e164, user_id_for
from app.store import FileStore, MemoryStore

PHONE = "+12055551234"
USER = "phone:+12055551234"
OTHER_PHONE = "+13105559876"


@pytest.fixture
def store(monkeypatch):
    """A clean in-memory store wired into main for the duration of a test."""
    fresh = MemoryStore()
    monkeypatch.setattr(main, "STORE", fresh)
    return fresh


@pytest.fixture
def file_store(tmp_path):
    return FileStore(tmp_path / "data")


# ==========================================================================
# Phone identity — one phone must never become two users
# ==========================================================================


class TestNormalizeE164:
    @pytest.mark.parametrize("raw", [
        "+12055551234",
        "12055551234",
        "2055551234",
        "(205) 555-1234",
        "205-555-1234",
        "  +1 205 555 1234  ",
        "+1 (205) 555-1234",
    ])
    def test_every_us_spelling_collapses_to_one_number(self, raw):
        assert normalize_e164(raw) == PHONE

    def test_same_phone_written_two_ways_is_one_user(self):
        assert user_id_for("2055551234") == user_id_for("+1 (205) 555-1234") == USER

    @pytest.mark.parametrize("raw", [None, "", "   ", "no digits here"])
    def test_unusable_handles_are_none(self, raw):
        assert normalize_e164(raw) is None

    def test_unusable_handle_still_yields_a_stable_user_id(self):
        assert user_id_for(None) == user_id_for("") == "phone:unknown"

    def test_apple_id_handles_survive_as_emails(self):
        # An email must not be mangled into digits — that would collapse every
        # Apple ID user onto "phone:unknown".
        assert normalize_e164("Buyer@Example.COM") == "buyer@example.com"
        assert normalize_e164("mailto:buyer@example.com") == "buyer@example.com"
        assert user_id_for("buyer@example.com") == "phone:buyer@example.com"

    def test_international_numbers_keep_their_country_code(self):
        assert normalize_e164("+442071838750") == "+442071838750"


# ==========================================================================
# Store protocol — identical behaviour across backends
# ==========================================================================


@pytest.fixture(params=["memory", "file"])
def any_store(request, tmp_path):
    return MemoryStore() if request.param == "memory" else FileStore(tmp_path / "d")


class TestStoreProtocol:
    def test_focus_starts_unset(self, any_store):
        assert any_store.get_focus(USER) is None

    def test_focus_round_trips(self, any_store):
        any_store.set_focus(USER, "deal-1")
        assert any_store.get_focus(USER) == "deal-1"

    def test_focus_is_per_user(self, any_store):
        any_store.set_focus(USER, "deal-1")
        assert any_store.get_focus("phone:+19995550000") is None

    def test_user_meta_starts_empty(self, any_store):
        assert any_store.get_user_meta(USER) == {}

    def test_user_meta_round_trips(self, any_store):
        any_store.set_user_meta(USER, {"last_card_kind": "LIST", "onboarded": True})
        assert any_store.get_user_meta(USER)["last_card_kind"] == "LIST"

    def test_user_meta_is_copied_not_aliased(self, any_store):
        meta = {"msg_times": [1.0]}
        any_store.set_user_meta(USER, meta)
        meta["msg_times"].append(2.0)          # mutate the caller's dict
        assert any_store.get_user_meta(USER)["msg_times"] == [1.0]

    def test_returned_meta_is_a_copy(self, any_store):
        any_store.set_user_meta(USER, {"onboarded": True})
        got = any_store.get_user_meta(USER)
        got["onboarded"] = False
        assert any_store.get_user_meta(USER)["onboarded"] is True

    def test_deleting_the_focused_deal_clears_focus(self, any_store):
        deal = Deal(user_id=USER, phone=PHONE)
        any_store.save_deal(deal)
        any_store.set_focus(USER, deal.id)
        any_store.delete_deal(deal.id)
        assert any_store.get_focus(USER) is None

    def test_deleting_another_deal_leaves_focus_alone(self, any_store):
        kept, gone = Deal(user_id=USER), Deal(user_id=USER)
        any_store.save_deal(kept)
        any_store.save_deal(gone)
        any_store.set_focus(USER, kept.id)
        any_store.delete_deal(gone.id)
        assert any_store.get_focus(USER) == kept.id

    def test_deals_are_isolated_by_user(self, any_store):
        any_store.save_deal(Deal(user_id=USER))
        any_store.save_deal(Deal(user_id="phone:" + OTHER_PHONE))
        assert len(any_store.list_deals(USER)) == 1


# ==========================================================================
# FileStore — the restart gate
# ==========================================================================


class TestFileStorePersistence:
    def test_deals_survive_a_restart(self, tmp_path):
        root = tmp_path / "data"
        first = FileStore(root)
        deal = Deal(user_id=USER, phone=PHONE, title="2019 Mazda CX-5", asking=16_000)
        first.save_deal(deal)

        revived = FileStore(root)              # simulate a backend restart
        got = revived.get_deal(deal.id)
        assert got is not None
        assert got.title == "2019 Mazda CX-5" and got.asking == 16_000

    def test_focus_and_meta_survive_a_restart(self, tmp_path):
        root = tmp_path / "data"
        first = FileStore(root)
        first.set_focus(USER, "deal-abc")
        first.set_user_meta(USER, {"onboarded": True})

        revived = FileStore(root)
        assert revived.get_focus(USER) == "deal-abc"
        assert revived.get_user_meta(USER) == {"onboarded": True}

    def test_negotiation_history_survives_a_restart(self, tmp_path):
        root = tmp_path / "data"
        first = FileStore(root)
        deal = Deal(user_id=USER, asking=16_000, R=13_000, V=14_200,
                    state=DealState.NEGOTIATING)
        deal.signals_log.append({"seller_price": 15_200, "concession_abs": 800,
                                 "firmness": 0.7, "bluff_claim": False,
                                 "final_claim": False, "walk_threat": False})
        deal.log_turn("seller", "I could do 15,200")
        first.save_deal(deal)

        revived = FileStore(root).get_deal(deal.id)
        assert len(revived.signals_log) == 1
        assert revived.belief() is not None      # replays cleanly off the log

    def test_user_ids_with_punctuation_round_trip(self, tmp_path):
        """`phone:+1205…` carries ':' and '+'; emails carry '@'."""
        root = tmp_path / "data"
        first = FileStore(root)
        for uid in ("phone:+12055551234", "phone:buyer@example.com", "phone:unknown"):
            first.set_focus(uid, f"deal-for-{uid}")

        revived = FileStore(root)
        for uid in ("phone:+12055551234", "phone:buyer@example.com", "phone:unknown"):
            assert revived.get_focus(uid) == f"deal-for-{uid}"

    def test_writes_leave_no_temp_files_behind(self, tmp_path):
        root = tmp_path / "data"
        store = FileStore(root)
        for _ in range(5):
            store.save_deal(Deal(user_id=USER))
        store.set_focus(USER, "x")
        leftovers = [p.name for p in root.rglob("*") if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_a_corrupt_deal_file_does_not_stop_boot(self, tmp_path):
        root = tmp_path / "data"
        store = FileStore(root)
        good = Deal(user_id=USER, title="survivor")
        store.save_deal(good)
        (root / "deals" / "broken.json").write_text("{ not json at all", encoding="utf-8")

        revived = FileStore(root)
        assert revived.get_deal(good.id).title == "survivor"

    def test_a_corrupt_user_file_does_not_stop_boot(self, tmp_path):
        root = tmp_path / "data"
        FileStore(root)
        (root / "users" / "garbage.json").write_text("<<<", encoding="utf-8")
        assert FileStore(root).get_focus(USER) is None

    def test_deleting_a_deal_removes_its_file(self, tmp_path):
        root = tmp_path / "data"
        store = FileStore(root)
        deal = Deal(user_id=USER)
        store.save_deal(deal)
        assert (root / "deals" / f"{deal.id}.json").exists()
        store.delete_deal(deal.id)
        assert not (root / "deals" / f"{deal.id}.json").exists()

    def test_deal_files_are_readable_json(self, tmp_path):
        """Debuggability: a human should be able to cat a deal mid-demo."""
        root = tmp_path / "data"
        store = FileStore(root)
        deal = Deal(user_id=USER, title="2019 Mazda CX-5")
        store.save_deal(deal)
        blob = json.loads((root / "deals" / f"{deal.id}.json").read_text())
        assert blob["title"] == "2019 Mazda CX-5"

    def test_store_selection_prefers_a_path_over_memory(self, tmp_path, monkeypatch):
        from app import store as store_mod
        monkeypatch.setenv("CLOSER_STORE_PATH", str(tmp_path / "sel"))
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
        store_mod.set_store(None)
        try:
            assert store_mod.backend_name() == "FileStore"
        finally:
            store_mod.set_store(None)

    def test_store_selection_falls_back_to_memory(self, monkeypatch):
        from app import store as store_mod
        monkeypatch.delenv("CLOSER_STORE_PATH", raising=False)
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
        monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
        store_mod.set_store(None)
        try:
            assert store_mod.backend_name() == "MemoryStore"
        finally:
            store_mod.set_store(None)


# ==========================================================================
# Focus resolution — the multi-deal gate
# ==========================================================================


class TestInboundDealResolution:
    def test_first_message_creates_a_deal_and_focuses_it(self, store):
        deal, parked = main._inbound_deal(USER, "chat-1", PHONE, "hey")
        assert parked is None
        assert store.get_focus(USER) == deal.id

    def test_first_link_fills_the_onboarding_shell(self, store):
        shell, _ = main._inbound_deal(USER, "chat-1", PHONE, "hi")
        deal, parked = main._inbound_deal(USER, "chat-1", PHONE,
                                          "https://cars.com/a")
        assert deal.id == shell.id      # don't orphan a brand-new user's shell
        assert parked is None

    def test_second_link_starts_a_second_deal_and_parks_the_first(self, store):
        first, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/a")
        first.listing_link = "https://cars.com/a"
        first.state = DealState.NEGOTIATING
        store.save_deal(first)

        second, parked = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/b")
        assert second.id != first.id
        assert parked is not None and parked.id == first.id
        assert store.get_focus(USER) == second.id       # focus on the second
        assert len(store.list_deals(USER)) == 2

    def test_a_relay_goes_to_the_focused_deal(self, store):
        first, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/a")
        first.listing_link, first.state = "https://cars.com/a", DealState.NEGOTIATING
        store.save_deal(first)
        second, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/b")

        deal, parked = main._inbound_deal(USER, "chat-1", PHONE, "he said 14000")
        assert deal.id == second.id and parked is None

    def test_focus_is_sticky_not_most_recent(self, store):
        """A user who switched back to an older deal stays there."""
        older, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/a")
        older.listing_link, older.state = "https://cars.com/a", DealState.NEGOTIATING
        store.save_deal(older)
        newer, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/b")
        newer.state = DealState.NEGOTIATING
        store.save_deal(newer)

        store.set_focus(USER, older.id)                 # an explicit SWITCH
        deal, _ = main._inbound_deal(USER, "chat-1", PHONE, "he said 14000")
        assert deal.id == older.id

    def test_a_link_never_wipes_a_closed_deal(self, store):
        """The deleted branch recycled a finished deal and destroyed the stats data."""
        closed, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/a")
        closed.listing_link = "https://cars.com/a"
        closed.state = DealState.CLOSED
        closed.closed_price = 13_440.0
        closed.signals_log.append({"seller_price": 14_000})
        store.save_deal(closed)

        new_deal, parked = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/b")
        survivor = store.get_deal(closed.id)
        assert new_deal.id != closed.id
        assert parked is None                     # a closed deal isn't "parked"
        assert survivor.closed_price == 13_440.0  # history intact
        assert survivor.signals_log

    def test_stale_focus_falls_back_instead_of_crashing(self, store):
        deal, _ = main._inbound_deal(USER, "chat-1", PHONE, "hi")
        store.set_focus(USER, "deal-that-no-longer-exists")
        resolved, _ = main._inbound_deal(USER, "chat-1", PHONE, "he said 14000")
        assert resolved.id == deal.id

    def test_an_active_deal_wins_over_a_more_recent_closed_one(self, store):
        active = Deal(user_id=USER, state=DealState.NEGOTIATING)
        store.save_deal(active)
        closed = Deal(user_id=USER, state=DealState.CLOSED)
        store.save_deal(closed)                    # saved later => more recent
        assert main._focused_deal(USER).id == active.id

    def test_two_phones_never_see_each_others_deals(self, store):
        mine, _ = main._inbound_deal(USER, "chat-1", PHONE, "https://cars.com/a")
        other_user = user_id_for(OTHER_PHONE)
        theirs, _ = main._inbound_deal(other_user, "chat-2", OTHER_PHONE,
                                       "https://cars.com/b")
        assert mine.id != theirs.id
        assert [d.id for d in store.list_deals(USER)] == [mine.id]
        assert [d.id for d in store.list_deals(other_user)] == [theirs.id]

    def test_routing_identifiers_are_backfilled(self, store):
        deal = Deal(user_id=USER)
        store.save_deal(deal)
        store.set_focus(USER, deal.id)
        resolved, _ = main._inbound_deal(USER, "chat-9", PHONE, "hello")
        assert resolved.chat_id == "chat-9" and resolved.phone == PHONE


# ==========================================================================
# closed_price + trajectory
# ==========================================================================


class TestClosedPriceAndTrajectory:
    def test_closing_freezes_the_price(self, store):
        deal = Deal(user_id=USER, asking=16_000, R=13_000, V=14_200,
                    state=DealState.NEGOTIATING, last_user_offer=13_440)
        store.save_deal(deal)
        main.route_message(deal, "deal, I'll take it", [], send=False)
        assert store.get_deal(deal.id).closed_price == 13_440

    def test_closed_price_is_not_recomputed_from_a_mutable_log(self, store):
        deal = Deal(user_id=USER, asking=16_000, R=13_000, V=14_200,
                    state=DealState.NEGOTIATING, last_user_offer=13_440)
        store.save_deal(deal)
        main.route_message(deal, "sold", [], send=False)
        deal.last_user_offer = 99_999          # as an UNDO would
        store.save_deal(deal)
        assert store.get_deal(deal.id).closed_price == 13_440

    def test_trajectory_is_empty_before_any_turn(self):
        assert Deal(user_id=USER).trajectory() == []

    def test_trajectory_has_one_row_per_closer_recommendation(self):
        deal = Deal(user_id=USER)
        deal.log_turn("seller", "15,200", signals={"seller_price": 15_200})
        deal.log_turn("closer", "counter", recommendation={
            "floor_point_est": 14_143, "floor_std": 540, "last_seller_price": 15_200,
            "offer": 13_440, "p_accept": 0.13, "action": "COUNTER"})
        deal.log_turn("closer", "just chatter")          # no recommendation
        rows = deal.trajectory()
        assert len(rows) == 1
        assert rows[0]["turn"] == 1
        assert rows[0]["floor_est"] == 14_143
        assert rows[0]["action"] == "COUNTER"
        assert rows[0]["signals"] == {"seller_price": 15_200}

    def test_trajectory_numbers_turns_consecutively(self):
        deal = Deal(user_id=USER)
        for i in range(3):
            deal.log_turn("seller", f"msg {i}", signals={"seller_price": 15_000 - i})
            deal.log_turn("closer", "rec", recommendation={"floor_point_est": 14_000 - i})
        assert [r["turn"] for r in deal.trajectory()] == [1, 2, 3]

    def test_trajectory_survives_feed_truncation(self):
        """UNDO truncates the feed; trajectory is a pure derivation over it."""
        deal = Deal(user_id=USER)
        for i in range(3):
            deal.log_turn("seller", f"m{i}", signals={"seller_price": 15_000})
            deal.log_turn("closer", "r", recommendation={"floor_point_est": 14_000 - i})
        deal.feed = deal.feed[:-2]
        assert len(deal.trajectory()) == 2

    def test_display_name_prefers_a_nickname(self):
        deal = Deal(user_id=USER, title="2019 Mazda CX-5")
        assert deal.display_name() == "2019 Mazda CX-5"
        deal.nickname = "the Mazda"
        assert deal.display_name() == "the Mazda"

    def test_public_carries_the_new_fields(self):
        deal = Deal(user_id=USER, title="t", nickname="n")
        pub = deal.public()
        assert pub["nickname"] == "n"
        assert pub["closed_price"] is None
        assert pub["trajectory"] == []
