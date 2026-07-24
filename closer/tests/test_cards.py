"""Card tests — update_1.md §4.6, §7 B2/B3.

Every card is rendered from `tests/fixtures/*.json`, which came out of the real
router driving the real `BeliefState` (see `build_fixtures.py`). So these assert
against numbers the engine actually produced, not numbers a test author liked.

Three groups matter more than the rest:

* **the bluff block** — the product, in four lines. It must fire on a turn that
  applied pressure and moved nothing, and must never fire otherwise.
* **the null states** — `snapshot is None`, `research is None`, no turns. That
  is what a judge sees in the first thirty seconds.
* **typography** — no markdown, no space-aligned columns. Both look broken on
  someone else's phone and neither shows up on the author's terminal.
"""

from __future__ import annotations

import re

import pytest

from app import cards
from app.state import Deal, DealState
from tests import fixtures


@pytest.fixture
def camry() -> Deal:
    return fixtures.load(fixtures.CAMRY)


@pytest.fixture
def civic() -> Deal:
    return fixtures.load(fixtures.CIVIC)


@pytest.fixture
def fresh() -> Deal:
    return fixtures.load(fixtures.FRESH)


@pytest.fixture
def f150() -> Deal:
    return fixtures.load(fixtures.F150)


@pytest.fixture
def tacoma() -> Deal:
    return fixtures.load(fixtures.TACOMA)


@pytest.fixture
def all_deals() -> list[Deal]:
    return fixtures.load_all()


ALL_CARDS = ("deal_card", "deal_list", "stats_card", "help_card", "onboarding")


# ── the fixtures are what they claim to be ───────────────────────────────────
def test_fixture_states(camry, civic, fresh, f150, tacoma) -> None:
    assert camry.state is DealState.NEGOTIATING and len(camry.feed) == 8
    assert civic.state is DealState.AWAITING_RESEARCH
    assert civic.snapshot is None and civic.research is None
    assert fresh.state is DealState.AWAITING_LINK
    assert (fresh.asking, fresh.V, fresh.R, fresh.snapshot, fresh.research) == \
        (None, None, None, None, None)
    assert f150.state is DealState.CLOSED
    assert tacoma.state is DealState.WALKED


def test_the_camry_arc_has_exactly_one_bluff(camry) -> None:
    bluffs = [t for t in camry.feed if (t.signals or {}).get("bluff_claim")]
    assert len(bluffs) == 1
    assert "coming to see it" in bluffs[0].text


# ── the money artifact ───────────────────────────────────────────────────────
def test_deal_card_has_every_block(camry) -> None:
    card = cards.deal_card(camry)
    assert "2008 Toyota Camry LE" in card
    assert "turn 4 of a live deal" in card
    assert "Listed $6,400" in card
    assert "they're at $5,400" in card
    assert "Their floor now reads $5,062" in card
    assert "Turn 1 it read $5,601" in card
    assert "down $539" in card
    assert "Confidence " in card and "±$188" in card
    assert "Zone of agreement" in card
    assert "Hold at $4,992" in card
    assert "41% they take it" in card


def test_deal_card_sparkline_is_wide_enough_to_read(camry) -> None:
    """Four blocks is a smudge in a proportional font at phone width. The
    series is step-held out to `SPARK_WIDTH` so the shape reads as a
    staircase — same data, more columns."""
    line = next(ln for ln in cards.deal_card(camry).splitlines()
                if ln.strip().startswith(tuple(cards.BLOCKS)))
    spark = line.split("  ")[0]
    assert len(spark) == cards.SPARK_WIDTH
    assert all(ch in cards.BLOCKS for ch in spark)
    assert line.endswith("turn 1 → 4")


def test_the_sparkline_plateau_shows_the_bluff(camry) -> None:
    """Turns 2 and 3 barely differ, so they must render as one flat run — that
    run IS the bluff, drawn."""
    line = next(ln for ln in cards.deal_card(camry).splitlines()
                if ln.strip().startswith(tuple(cards.BLOCKS)))
    spark = line.split("  ")[0]
    runs = [len(list(g)) for _, g in __import__("itertools").groupby(spark)]
    assert max(runs) >= 6, f"turns 2-3 should merge into one plateau: {spark}"


def test_the_bluff_block_fires_and_names_the_turn(camry) -> None:
    """The whole pitch: pressure applied on turn 3, posterior moved $4."""
    card = cards.deal_card(camry)
    assert "🎣 Turn 3" in card
    assert "That was a bluff." in card
    assert "The curve moved $4." in card
    assert "coming to see it Saturday" in card, "quote the seller, don't template"


def test_the_bluff_quote_strips_the_relay_preamble(camry) -> None:
    """The user types "he says X"; the card quotes X."""
    quoted = re.search(r'🎣 Turn \d+ — "(.*)"', cards.deal_card(camry)).group(1)
    assert not quoted.lower().startswith(("he says", "he said", "they say"))


def test_the_bluff_block_needs_both_halves_of_the_conjunction(camry) -> None:
    """`bluff_claim` alone is not a bluff. If the floor moved, they moved.

    Turn 3 keeps its `bluff_claim`; only its floor estimate changes, by more
    than 1% of the $6,400 ask. The block must disappear.
    """
    bluff_turn = next(i for i, t in enumerate(camry.feed)
                      if (t.signals or {}).get("bluff_claim"))
    camry.feed[bluff_turn + 1].recommendation["floor_point_est"] = 4_000.0
    assert (camry.feed[bluff_turn].signals or {})["bluff_claim"] is True
    assert "That was a bluff." not in cards.deal_card(camry)


def test_no_bluff_claim_means_no_bluff_block(camry) -> None:
    for turn in camry.feed:
        if turn.signals:
            turn.signals["bluff_claim"] = False
    assert "🎣" not in cards.deal_card(camry)


def test_the_bluff_block_is_never_faked(f150, tacoma) -> None:
    """Neither of these arcs contains a bluff. Neither card may claim one."""
    assert "That was a bluff." not in cards.deal_card(f150)
    assert "That was a bluff." not in cards.deal_card(tacoma)


def test_turn_one_can_never_be_a_bluff() -> None:
    """There is no prior estimate for the opening turn to have failed to move."""
    deal = fixtures.load(fixtures.CAMRY)
    deal.feed = deal.feed[:2]                       # one seller turn, one closer turn
    deal.feed[0].signals["bluff_claim"] = True
    assert "🎣" not in cards.deal_card(deal)


# ── the null states: what a judge sees first ─────────────────────────────────
def test_deal_card_on_a_brand_new_deal(fresh) -> None:
    card = cards.deal_card(fresh)
    assert card.strip()
    assert "listing" in card.lower()
    assert "$" not in card, "no money before there is any money"
    assert "None" not in card and "nan" not in card


def test_deal_card_while_researching(civic) -> None:
    card = cards.deal_card(civic)
    assert "🔎" in card and "2016 Honda Civic EX" in card
    assert "$11,900" in card
    assert "kbb.com/honda/civic/2016/" in card, "stream the trace, don't hide it"
    assert "None" not in card


def test_deal_card_with_research_but_no_turns(camry) -> None:
    camry.feed, camry.snapshot = [], None
    card = cards.deal_card(camry)
    assert "No turns yet" in card
    assert "$5,200" in card                          # fair value still known
    assert "None" not in card


def test_every_card_survives_a_stripped_deal() -> None:
    """A `Deal` with nothing but the required fields must not raise."""
    bare = Deal(user_id="phone:+12055550100")
    for fn in (cards.deal_card,):
        assert fn(bare).strip()
    assert cards.deal_list([bare], bare.id).strip()
    assert cards.stats_card([bare]).strip()


@pytest.mark.parametrize("name", fixtures.ALL)
def test_no_card_ever_leaks_a_none_or_a_nan(name: str) -> None:
    deal = fixtures.load(name)
    for text in (cards.deal_card(deal), cards.deal_list([deal], deal.id),
                 cards.stats_card([deal])):
        assert "None" not in text
        assert "nan" not in text.lower().replace("financ", "")
        assert "$0" not in text


# ── outcomes ─────────────────────────────────────────────────────────────────
def test_closed_card_leads_with_what_you_paid(f150) -> None:
    card = cards.deal_card(f150)
    assert "🤝" in card and "closed" in card
    assert "You paid $12,516" in card
    assert "$2,384 under ask (16%)" in card
    assert "they're at" not in card, "on a closed deal only the paid price matters"


def test_walked_card_is_honest_about_the_number(tacoma) -> None:
    card = cards.deal_card(tacoma)
    assert "🚶" in card and "You walked." in card
    assert "$800 over" in card
    assert "saved" not in card.lower(), "walking is not saving (§4.5)"


# ── the deal list ────────────────────────────────────────────────────────────
def test_deal_list_numbers_and_marks_focus(all_deals) -> None:
    text = cards.deal_list(all_deals, all_deals[0].id)
    lines = text.splitlines()
    assert lines[0] == "📋 Your deals"
    assert any(ln.startswith("▶ 1. 2008 Toyota Camry LE") for ln in lines)
    for i in range(2, len(all_deals) + 1):
        assert any(ln.strip().startswith(f"{i}.") for ln in lines)
    assert sum(ln.startswith("▶") for ln in lines) == 1


def test_deal_list_focus_marker_moves(all_deals) -> None:
    text = cards.deal_list(all_deals, all_deals[2].id)
    assert any(ln.startswith("▶ 3.") for ln in text.splitlines())


def test_deal_list_without_focus_marks_nothing(all_deals) -> None:
    assert "▶" not in cards.deal_list(all_deals, None)


def test_deal_list_says_what_each_deal_is_doing(all_deals) -> None:
    text = cards.deal_list(all_deals, all_deals[0].id)
    assert "negotiating, turn 4" in text
    assert "researching…" in text
    assert "closed" in text and "saved $2,384" in text
    assert "walked" in text and "$800 over fair value" in text
    assert "$6,400 ask · hold at $4,992 next" in text


def test_list_rows_carry_no_trailing_emoji(all_deals) -> None:
    """A long title plus a trailing glyph wraps at 390px and strands the emoji
    on its own line. Only the header may carry one."""
    lines = cards.deal_list(all_deals, all_deals[0].id).splitlines()
    for line in lines[1:]:
        assert not line.rstrip().endswith(("🤝", "🚶", "🚗", "🔎")), line


def test_deal_list_hint_names_a_deal_you_can_actually_switch_to(all_deals) -> None:
    """The hint has to survive `intent.resolve_switch`, or it teaches a lie."""
    from app.intent import classify, resolve_switch

    hint = cards.deal_list(all_deals, all_deals[0].id).splitlines()[-1]
    phrase = re.search(r'say "(switch to the \w+)"', hint).group(1)
    got = classify(phrase)
    deal, candidates = resolve_switch(got.arg, all_deals)
    assert deal is not None and candidates == []
    assert deal.id != all_deals[0].id, "a hint that switches to where you are is noise"


def test_deal_list_empty() -> None:
    text = cards.deal_list([], None)
    assert "No deals yet" in text and "link" in text


@pytest.mark.parametrize("name,word", [(fixtures.FRESH, "waiting on a link"),
                                       (fixtures.TACOMA, "walked")])
def test_deal_list_never_repeats_a_state_label(name: str, word: str) -> None:
    """A detail line that restates the state reads as a stutter on a phone."""
    deal = fixtures.load(name)
    assert cards.deal_list([deal], deal.id).count(word) == 1


# ── savings math, §4.5 ───────────────────────────────────────────────────────
def test_stats_card_sums_only_closed_deals(all_deals) -> None:
    text = cards.stats_card(all_deals)
    assert "$2,384 saved across 1 closed deal" in text
    assert "16% under ask" in text


def test_walked_money_never_enters_the_headline(all_deals) -> None:
    """`avoided` is real but gets its own line, phrased honestly (§4.5)."""
    text = cards.stats_card(all_deals)
    assert "Walked once — $800 over fair value" in text
    assert "$3,184" not in text, "2,384 + 800 must never appear as one number"


def test_open_deals_are_projected_never_saved(camry, civic) -> None:
    text = cards.stats_card([camry, civic])
    assert "saved" not in text.lower()
    assert "on the table" in text
    assert "projected, not banked" in text


def test_stats_card_counts(all_deals) -> None:
    text = cards.stats_card(all_deals)
    assert "5 deals total" in text
    assert "3 live" in text
    assert "turns to close" in text


def test_stats_card_reports_time_spent(all_deals) -> None:
    assert re.search(r"You've spent about \d+ minutes texting me\.",
                     cards.stats_card(all_deals))


def test_time_spent_is_capped_per_deal(f150) -> None:
    """A deal left open over a weekend did not cost a weekend of texting."""
    f150.updated_at = f150.created_at + 60 * 60 * 72
    assert cards._minutes([f150]) == cards._MAX_MINUTES_PER_DEAL


def test_stats_card_picks_a_best_only_when_there_is_a_contest(all_deals) -> None:
    assert "🏆" not in cards.stats_card(all_deals)      # one closed deal
    second = fixtures.load(fixtures.F150)
    second.id, second.title, second.asking = "zz", "2019 Subaru Outback", 20_000.0
    text = cards.stats_card(all_deals + [second])
    assert "🏆 Best: 2019 Subaru Outback" in text
    assert "2 closed deals" in text and "on average" in text


def test_stats_card_empty() -> None:
    text = cards.stats_card([])
    assert "Nothing yet" in text and "$" not in text


def test_saved_formula(f150) -> None:
    assert cards._saved(f150) == pytest.approx(f150.asking - f150.last_user_offer)


def test_avoided_formula(tacoma) -> None:
    assert cards._avoided(tacoma) == pytest.approx(tacoma.last_seller_price - tacoma.V)


def test_saved_and_avoided_only_apply_to_their_own_state(camry, f150, tacoma) -> None:
    assert cards._saved(camry) is None and cards._avoided(camry) is None
    assert cards._avoided(f150) is None
    assert cards._saved(tacoma) is None


def test_closed_price_is_preferred_over_the_derivation(f150) -> None:
    """Once Lane A persists `closed_price` (§4.3), it wins — a later UNDO can
    change the log the fallback recomputes from."""
    object.__setattr__(f150, "__dict__",
                       {**f150.__dict__, "closed_price": 11_000.0})
    assert cards._closed_price(f150) == 11_000.0
    assert cards._saved(f150) == pytest.approx(3_900.0)


# ── trajectory: works with or without Lane A's method ────────────────────────
def test_trajectory_is_derived_when_the_model_lacks_the_method(camry) -> None:
    traj = cards._trajectory(camry)
    assert [t["turn"] for t in traj] == [1, 2, 3, 4]
    assert [round(t["floor_est"]) for t in traj] == [5601, 5323, 5327, 5062]
    assert traj[2]["signals"]["bluff_claim"] is True
    assert traj[0]["signals"]["seller_price"] == 6400.0


def test_trajectory_prefers_the_model_method_when_it_exists(camry) -> None:
    sentinel = [{"turn": 1, "floor_est": 1.0, "signals": None}]
    object.__setattr__(camry, "__dict__",
                       {**camry.__dict__, "trajectory": lambda: sentinel})
    assert cards._trajectory(camry) == sentinel


def test_trajectory_skips_closer_turns_with_no_recommendation(f150) -> None:
    """`route_message` logs plain replies too; only real turns count."""
    plain = [t for t in f150.feed if t.role == "closer" and not t.recommendation]
    assert plain, "fixture should contain the close confirmation"
    assert len(cards._trajectory(f150)) == 3


# ── glyph helpers ────────────────────────────────────────────────────────────
def test_sparkline_gives_equal_values_equal_glyphs() -> None:
    """The bluff turn's whole job is looking identical to the one before it."""
    spark = cards.sparkline([5601, 5323, 5327, 5062])
    assert spark[1] == spark[2]
    assert spark[0] == cards.BLOCKS[-1] and spark[3] == cards.BLOCKS[0]


def test_sparkline_handles_a_flat_series() -> None:
    assert cards.sparkline([100, 100, 100]) == cards.BLOCKS[4] * 3


def test_sparkline_handles_empty_and_none() -> None:
    assert cards.sparkline([]) == ""
    assert cards.sparkline([None, None]) == ""
    assert len(cards.sparkline([1, None, 3])) == 2


def test_sparkline_glyphs_stay_in_the_ramp() -> None:
    assert set(cards.sparkline(range(50))) <= set(cards.BLOCKS)


def test_meter() -> None:
    assert cards.meter(4) == "●●●●○"
    assert cards.meter(0) == "○○○○○"
    assert cards.meter(9) == "●●●●●"
    assert cards.meter(-1) == "○○○○○"


def test_confidence_scales_with_the_asking_price() -> None:
    """±$300 is tight on a $40k truck and noise on a $6k Camry."""
    assert cards.confidence_dots(300, 40_000) > cards.confidence_dots(300, 6_000)
    assert cards.confidence_dots(None, 6_000) == 0
    assert cards.confidence_dots(300, None) == 0
    assert cards.confidence_dots(188, 6400) == 4


# ── typography (§4.6) and voice (§7 B3) ──────────────────────────────────────
def every_rendering(deals: list[Deal]) -> list[tuple[str, str]]:
    out = [(f"deal_card[{d.title}]", cards.deal_card(d)) for d in deals]
    out += [
        ("deal_list", cards.deal_list(deals, deals[0].id)),
        ("deal_list.empty", cards.deal_list([], None)),
        ("stats_card", cards.stats_card(deals)),
        ("stats_card.empty", cards.stats_card([])),
        ("help_card", cards.help_card()),
        ("onboarding", cards.onboarding()),
        ("no_deals", cards.no_deals()),
        ("deal_parked", cards.deal_parked(deals[1], deals[0])),
        ("switched", cards.switched(deals[0])),
        ("ambiguous_switch", cards.ambiguous_switch("camry", deals[:2])),
        ("no_match", cards.no_match("porsche")),
        ("confirm_delete", cards.confirm_delete(deals[0])),
        ("deleted", cards.deleted("Civic")),
        ("renamed", cards.renamed(deals[0])),
        ("undone", cards.undone(deals[0])),
        ("deal_limit", cards.deal_limit(10)),
        ("throttled", cards.throttled()),
        ("research_blocked", cards.research_blocked(deals[1])),
        ("research_started", cards.research_started("https://cars.com/x")),
        ("no_focus", cards.no_focus()),
        ("not_negotiating", cards.not_negotiating(deals[1])),
        ("unparsed", cards.unparsed()),
        ("closed_message", cards.closed_message(deals[2])),
        ("walked_message", cards.walked_message(deals[3])),
        ("error", cards.error()),
    ]
    return out


def test_nothing_uses_markdown(all_deals) -> None:
    """iMessage renders none of it — `**bold**` arrives as literal asterisks."""
    for name, text in every_rendering(all_deals):
        assert "**" not in text and "__" not in text, name
        assert not re.search(r"^\s*#{1,6}\s", text, re.M), name
        assert not re.search(r"\[[^\]]+\]\([^)]+\)", text), name
        assert "`" not in text, name


def test_nothing_builds_a_column_out_of_spaces(all_deals) -> None:
    """A proportional font will not align them, and the demo looks broken on
    the judge's phone. Runs of 2+ interior spaces are the tell; the fixed
    continuation indent is at the start of a line and is not a column.

    The one allowed interior run is the gap after the sparkline. It separates
    two things on one line — nothing above or below has to line up with it — so
    a proportional font cannot break it.
    """
    allowed = re.compile(r"^[" + cards.BLOCKS + r"]+ {2}turn \d+ → \d+$")
    for name, text in every_rendering(all_deals):
        for line in text.splitlines():
            body = line.lstrip()
            if allowed.match(body):
                continue
            assert "  " not in body, f"{name}: {line!r}"
            assert "\t" not in line, name


def test_indentation_is_the_one_documented_width(all_deals) -> None:
    for name, text in every_rendering(all_deals):
        for line in text.splitlines():
            lead = len(line) - len(line.lstrip(" "))
            assert lead in (0, 2, 3, 6), f"{name}: {lead} spaces in {line!r}"


def test_nothing_is_empty(all_deals) -> None:
    for name, text in every_rendering(all_deals):
        assert text.strip(), name


def test_the_voice_never_slips(all_deals) -> None:
    """§7 B3: a sharp friend who has done this a hundred times. Never apologise,
    never say "I'm an AI", never hedge into a range."""
    banned = ("i'm an ai", "i am an ai", "as an ai", "language model",
              "i'm sorry", "i am sorry", "apologies", "unfortunately",
              "please note", "kindly", "i cannot", "somewhere between")
    for name, text in every_rendering(all_deals):
        low = text.lower()
        for phrase in banned:
            assert phrase not in low, f"{name}: {phrase!r}"


def test_onboarding_says_what_to_do_next() -> None:
    text = cards.onboarding()
    assert "Closer" in text
    assert "link" in text.lower()
    assert '"help"' in text


def test_help_card_covers_the_grammar() -> None:
    """Every intent a user can reach must be discoverable from `help`."""
    text = cards.help_card().lower()
    for word in ("card", "deals", "stats", "undo", "deal", "walked", "delete"):
        assert word in text, word


def test_help_card_is_routable() -> None:
    """The phrases `help` advertises must classify as what it says they do."""
    from app.intent import Intent, classify

    expected = {"card": Intent.CARD, "deals": Intent.LIST, "stats": Intent.STATS,
                "undo": Intent.UNDO, "we have a deal": Intent.CLOSE,
                "I walked": Intent.WALK, "delete the Civic": Intent.DELETE,
                "call this the red Civic": Intent.RENAME}
    text = cards.help_card().lower()
    for phrase, intent in expected.items():
        assert f'"{phrase.lower()}"' in text, f"help never mentions {phrase!r}"
        assert classify(phrase).intent is intent, phrase


def test_research_blocked_names_the_site_and_asks_one_question(civic) -> None:
    text = cards.research_blocked(civic)
    assert "cars.com" in text
    assert "asking" in text
    assert text.count("?") == 1, "ask one thing"


def test_undone_restates_the_number(camry) -> None:
    assert "$4,992" in cards.undone(camry)


def test_undone_on_a_deal_with_nothing_left(fresh) -> None:
    assert cards.undone(fresh).strip()


def test_deal_parked_names_both_deals(camry, civic) -> None:
    text = cards.deal_parked(civic, camry)
    assert "2016 Honda Civic EX" in text and "2008 Toyota Camry LE" in text
    assert "parked" in text


def test_ambiguous_switch_asks_instead_of_guessing(all_deals) -> None:
    text = cards.ambiguous_switch("camry", all_deals[:2])
    assert "1." in text and "2." in text
    assert text.rstrip().endswith("Reply with the number.")


def test_closed_and_walked_messages_carry_the_money(f150, tacoma) -> None:
    assert "$12,516" in cards.closed_message(f150)
    assert "$2,384 under ask" in cards.closed_message(f150)
    assert "$800 over fair value" in cards.walked_message(tacoma)


# ── nickname (§4.3), read defensively until Lane A lands it ──────────────────
def test_nickname_wins_over_title(camry) -> None:
    object.__setattr__(camry, "__dict__", {**camry.__dict__, "nickname": "the beater"})
    assert "the beater" in cards.deal_card(camry)
    assert "2008 Toyota Camry LE" not in cards.deal_card(camry)


def test_missing_nickname_falls_back_to_title(camry) -> None:
    assert not hasattr(camry, "nickname")
    assert "2008 Toyota Camry LE" in cards.deal_card(camry)
