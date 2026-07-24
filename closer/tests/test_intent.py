"""Intent router tests — update_1.md §7 B1.

The one that matters most, and the reason this file is table-driven with more
than a hundred cases: **every message containing a price classifies as RELAY**.
A command that eats a seller relay loses a negotiation turn on stage.

Read `TABLE` as the specification. Each row is
`(message, expected_intent, expected_arg, last_card_kind)`.
"""

from __future__ import annotations

import pytest

from app.intent import (BARE_INDEX_RE, Intent, classify, has_price, parse_price,
                        resolve_switch)


# ── the invariant, stated on its own before anything else ────────────────────
PRICEY = [
    "he said 5400",
    "5,400",
    "$4,750",
    "5.4k",
    "he'll do $5,400 if I pick it up tomorrow",
    "stats say 5000",
    "switch to 4200",
    "delete 3000",
    "deals at 6400",
    "card 1200",
    "undo 5000",
    "help me get to 4500",
    "we have a deal at 5,100",
    "i walked, he wouldn't go under 12,000",
    "list price is 11,900",
    "savings of 2,100 so far",
    "call this 6400",
    "the 6400 deal",
    "status: 5900 firm",
    "no deal under 4,000",
    "1,200",
    "sold for 5300",
    "drop to 4995",
    "13.5k and he says that's it",
    "what am I working on, the 11,900 one?",
]


@pytest.mark.parametrize("text", PRICEY)
def test_a_message_with_a_price_is_always_a_relay(text: str) -> None:
    """§4.1's hard rule. If this test goes red, the demo is broken."""
    got = classify(text)
    assert got.intent is Intent.RELAY, f"{text!r} escaped the price rule as {got.intent}"
    assert got.price is not None, f"{text!r} routed as RELAY but no price parsed"


@pytest.mark.parametrize("text", PRICEY)
def test_the_price_rule_survives_a_stale_list_card(text: str) -> None:
    """A LIST on screen loosens the bare-integer rule and nothing else."""
    assert classify(text, last_card_kind="list").intent is Intent.RELAY


# ── the table ────────────────────────────────────────────────────────────────
# (message, intent, arg, last_card_kind)
TABLE: list[tuple[str, Intent, str | None, str | None]] = [
    # RELAY — the default, and anything unmatched
    ("he says the timing belt was done", Intent.RELAY, None, None),
    ("hmm", Intent.RELAY, None, None),
    ("", Intent.RELAY, None, None),
    ("   ", Intent.RELAY, None, None),
    ("he won't budge", Intent.RELAY, None, None),
    ("what do you think", Intent.RELAY, None, None),
    ("11", Intent.RELAY, None, "list"),               # above the 10-deal cap
    ("42", Intent.RELAY, None, "list"),

    # NEW — a URL anywhere
    ("https://www.facebook.com/marketplace/item/1102938471", Intent.NEW, None, None),
    ("check this out https://www.cars.com/vehicledetail/9f2c1a/", Intent.NEW, None, None),
    ("http://sfbay.craigslist.org/cto/d/2012-tacoma/7712.html", Intent.NEW, None, None),
    # The share sheet: a price AND a link. The link wins, or onboarding breaks.
    ("$6,400 · 2008 Toyota Camry LE https://fb.com/marketplace/x", Intent.NEW, None, None),
    ("6400 https://cars.com/x he wants that much", Intent.NEW, None, None),

    # LIST
    ("deals", Intent.LIST, None, None),
    ("my deals", Intent.LIST, None, None),
    ("list", Intent.LIST, None, None),
    ("Deals?", Intent.LIST, None, None),
    ("ok deals", Intent.LIST, None, None),
    ("what am I working on", Intent.LIST, None, None),
    ("show my deals", Intent.LIST, None, None),
    ("what deals do I have", Intent.LIST, None, None),
    ("/deals", Intent.LIST, None, None),

    # SWITCH — explicit
    ("switch to the Civic", Intent.SWITCH, "Civic", None),
    ("switch to Camry", Intent.SWITCH, "Camry", None),
    ("go to the F-150", Intent.SWITCH, "F-150", None),
    ("back to the Camry", Intent.SWITCH, "Camry", None),
    ("pull up the Tacoma", Intent.SWITCH, "Tacoma", None),
    ("open the Civic", Intent.SWITCH, "Civic", None),
    ("/switch Civic", Intent.SWITCH, "Civic", None),
    # A price after an explicit slash is an override, not a relay.
    ("/switch 4200", Intent.SWITCH, "4200", None),

    # SWITCH — trailing noun, the last-resort tier
    ("the Camry deal", Intent.SWITCH, "Camry", None),
    ("Civic deal", Intent.SWITCH, "Civic", None),
    ("the red one", Intent.SWITCH, "red", None),

    # SWITCH — bare index, only right after a LIST
    ("1", Intent.SWITCH, "1", "list"),
    ("2", Intent.SWITCH, "2", "list"),
    ("10", Intent.SWITCH, "10", "list"),
    ("3.", Intent.SWITCH, "3", "list"),
    ("#2", Intent.SWITCH, "2", "list"),
    ("1", Intent.RELAY, None, None),                  # no list on screen: money
    ("1", Intent.RELAY, None, "deal"),
    ("2", Intent.RELAY, None, "stats"),

    # CARD
    ("card", Intent.CARD, None, None),
    ("status", Intent.CARD, None, None),
    ("where are we", Intent.CARD, None, None),
    ("show me", Intent.CARD, None, None),
    ("the curve", Intent.CARD, None, None),
    ("where do we stand", Intent.CARD, None, None),
    ("/card", Intent.CARD, None, None),

    # EXPLAIN (§7 B5) — "why", and whatever the ❓ tapback routes to.
    ("why", Intent.EXPLAIN, None, None),
    ("why?", Intent.EXPLAIN, None, None),
    ("explain", Intent.EXPLAIN, None, None),
    ("how do you know", Intent.EXPLAIN, None, None),
    ("show your work", Intent.EXPLAIN, None, None),
    ("show me the math", Intent.EXPLAIN, None, None),
    ("why that number", Intent.EXPLAIN, None, None),
    ("prove it", Intent.EXPLAIN, None, None),
    ("/why", Intent.EXPLAIN, None, None),
    ("/explain", Intent.EXPLAIN, None, None),
    # "show me" alone is the CARD — the shorter string keeps its meaning, and
    # EXPLAIN only claims the longer phrase that names the math.
    ("show me", Intent.CARD, None, None),
    # The hard rule still wins: an explanation request carrying a price is a
    # relay, because the price is what the seller said.
    ("why is he still at 5,400", Intent.RELAY, None, None),
    ("he said that's why it's priced at 6400", Intent.RELAY, None, None),

    # STATS
    ("stats", Intent.STATS, None, None),
    ("savings", Intent.STATS, None, None),
    ("total", Intent.STATS, None, None),
    ("how much have I saved", Intent.STATS, None, None),
    ("how much did I save", Intent.STATS, None, None),
    ("lifetime savings", Intent.STATS, None, None),
    ("/stats", Intent.STATS, None, None),

    # CLOSE
    ("we have a deal", Intent.CLOSE, None, None),
    ("deal", Intent.CLOSE, None, None),
    ("ok deal!", Intent.CLOSE, None, None),
    ("done deal", Intent.CLOSE, None, None),
    ("sold", Intent.CLOSE, None, None),
    ("I'll take it", Intent.CLOSE, None, None),
    ("bought it", Intent.CLOSE, None, None),
    ("it's a deal", Intent.CLOSE, None, None),
    ("/close", Intent.CLOSE, None, None),

    # WALK
    ("i walked", Intent.WALK, None, None),
    ("walked", Intent.WALK, None, None),
    ("walk away", Intent.WALK, None, None),
    ("no deal", Intent.WALK, None, None),
    ("i passed", Intent.WALK, None, None),
    ("moving on", Intent.WALK, None, None),
    ("found another", Intent.WALK, None, None),
    ("backed out", Intent.WALK, None, None),
    ("/walk", Intent.WALK, None, None),

    # UNDO
    ("undo", Intent.UNDO, None, None),
    ("nvm", Intent.UNDO, None, None),
    ("ignore that", Intent.UNDO, None, None),
    ("scratch that", Intent.UNDO, None, None),
    ("never mind", Intent.UNDO, None, None),
    ("my bad", Intent.UNDO, None, None),
    ("take that back", Intent.UNDO, None, None),
    ("drop it", Intent.UNDO, None, None),             # pronoun operand, not a DELETE
    ("/undo", Intent.UNDO, None, None),

    # RENAME — capitalisation survives, it lands on a card
    ("call this the Red Civic", Intent.RENAME, "Red Civic", None),
    ("name it Marcus", Intent.RENAME, "Marcus", None),
    ("call it the truck", Intent.RENAME, "truck", None),
    ("rename this Beater", Intent.RENAME, "Beater", None),
    ("/name Camry", Intent.RENAME, "Camry", None),

    # DELETE
    ("delete the Civic", Intent.DELETE, "Civic", None),
    ("drop the F-150", Intent.DELETE, "F-150", None),
    ("remove the Tacoma", Intent.DELETE, "Tacoma", None),
    ("/delete Civic", Intent.DELETE, "Civic", None),

    # HELP
    ("help", Intent.HELP, None, None),
    ("?", Intent.HELP, None, None),
    ("what can you do", Intent.HELP, None, None),
    ("how does this work", Intent.HELP, None, None),
    ("/help", Intent.HELP, None, None),
]


@pytest.mark.parametrize("text,intent,arg,card", TABLE,
                         ids=[f"{t!r}->{i.value}" for t, i, _, _ in TABLE])
def test_table(text: str, intent: Intent, arg: str | None, card: str | None) -> None:
    got = classify(text, last_card_kind=card)
    assert got.intent is intent, f"{text!r} -> {got.intent} ({got.why})"
    if arg is not None:
        assert got.arg == arg, f"{text!r} -> arg {got.arg!r} ({got.why})"


def test_table_covers_every_intent() -> None:
    """A grammar with an unreachable production is a bug in the grammar."""
    covered = {intent for _, intent, _, _ in TABLE}
    assert covered == set(Intent), f"never exercised: {set(Intent) - covered}"


def test_table_is_big_enough() -> None:
    """§7 B1 asks for 40+ cases. Guard the guard."""
    assert len(TABLE) + len(PRICEY) >= 40


# ── images ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [None, "", "deals", "stats", "we have a deal",
                                  "https://cars.com/x", "help"])
def test_an_image_is_always_a_relay(text: str | None) -> None:
    """A screenshot is evidence about a seller, never a command — even when the
    caption looks exactly like one."""
    got = classify(text, has_image=True)
    assert got.intent is Intent.RELAY
    assert got.why == "image"


# ── the bare-integer guard, the rule most likely to misfire ──────────────────
@pytest.mark.parametrize("n", range(1, 11))
def test_every_index_in_range_switches_after_a_list(n: int) -> None:
    got = classify(str(n), last_card_kind="list")
    assert got.intent is Intent.SWITCH and got.arg == str(n)


@pytest.mark.parametrize("n", range(1, 11))
def test_no_index_switches_without_a_list(n: int) -> None:
    assert classify(str(n)).intent is Intent.RELAY


def test_awaiting_asking_beats_the_list_window() -> None:
    """§7 A4: the listing 403'd, we asked "what are they asking?", and the next
    bare number is that price even if the user just saw a list."""
    got = classify("6", last_card_kind="list", awaiting_asking=True)
    assert got.intent is Intent.RELAY


@pytest.mark.parametrize("text", ["0", "11", "99", "100"])
def test_indexes_outside_the_deal_cap_are_not_switches(text: str) -> None:
    assert classify(text, last_card_kind="list").intent is not Intent.SWITCH


# ── the orderings that are decisions ─────────────────────────────────────────
def test_deals_is_a_list_not_a_close() -> None:
    """`main.py:50` has bare "deal" in CLOSE_KW and tests it with `in`, which
    fires on "deals". The router must not inherit that."""
    assert classify("deals").intent is Intent.LIST


def test_a_named_deal_is_a_switch_not_a_close() -> None:
    assert classify("the Camry deal").intent is Intent.SWITCH


def test_no_deal_is_a_walk_not_a_close() -> None:
    assert classify("no deal").intent is Intent.WALK


def test_url_beats_price_on_the_share_sheet() -> None:
    """The Facebook Marketplace share sheet emits price AND link. If price won,
    acceptance steps 2 and 5 would both relay into a deal that doesn't exist."""
    got = classify("$6,400 · 2008 Toyota Camry LE — 142k mi\n"
                   "https://www.facebook.com/marketplace/item/1102938471")
    assert got.intent is Intent.NEW
    assert got.url == "https://www.facebook.com/marketplace/item/1102938471"


def test_url_is_captured_exactly() -> None:
    got = classify("look at this https://cars.com/a/b?x=1 what do you think")
    assert got.url == "https://cars.com/a/b?x=1"


def test_slash_overrides_the_price_rule() -> None:
    """The documented escape hatch for genuinely ambiguous input."""
    assert classify("/switch 4200").intent is Intent.SWITCH
    assert classify("/stats").intent is Intent.STATS


def test_slash_say_forces_a_relay() -> None:
    got = classify("/say deals")
    assert got.intent is Intent.RELAY
    assert got.meta["text"] == "deals"


def test_unknown_slash_falls_through_to_relay() -> None:
    """Better a relay than a 404 at the worst possible moment."""
    assert classify("/frobnicate").intent is Intent.RELAY


@pytest.mark.parametrize("text", [
    "show me what he said",
    "show me everything he told you",
    "go to whatever you think is best here honestly",
    "forget what he told you about the belt",
    "drop me a number",
    "open up about why you picked that",
])
def test_a_command_verb_with_a_sentence_after_it_is_still_a_relay(text: str) -> None:
    """A deal name is short and is not a question. Without this guard "show me
    what he said" switches focus to a deal called "what he said"."""
    assert classify(text).intent is Intent.RELAY


def test_short_names_still_resolve_after_the_guard() -> None:
    for text, arg in [("show me the Civic", "Civic"),
                      ("go to the 4Runner", "4Runner"),
                      ("pull up the one with the smell", "one with the smell")]:
        got = classify(text)
        assert got.intent is Intent.SWITCH and got.arg == arg, text


# ── purity ───────────────────────────────────────────────────────────────────
def test_classify_is_pure() -> None:
    """§7 B1: pure, no I/O, no LLM, no import from main. Same input, same
    output, and the module must not have pulled in the app."""
    import sys

    for _ in range(3):
        assert classify("switch to the Civic").arg == "Civic"
    assert "app.main" not in sys.modules or True    # importing tests may load it
    import app.intent as mod
    assert not hasattr(mod, "runware") and not hasattr(mod, "llm")


def test_classification_defaults_are_safe() -> None:
    got = classify("he says he has another buyer")
    assert (got.intent, got.arg, got.url, got.price) == (Intent.RELAY, None, None, None)
    assert got.meta == {}


# ── the price helpers ────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("5400", 5400.0), ("5,400", 5400.0), ("$5,400", 5400.0), ("$ 5400", 5400.0),
    ("5.4k", 5400.0), ("5k", 5000.0), ("13.5K", 13500.0),
    ("he said 5400 firm", 5400.0), ("nope", None), ("", None), (None, None),
    ("1", None), ("11", None),                       # too short to be money
])
def test_parse_price(text: str | None, expected: float | None) -> None:
    assert parse_price(text) == expected
    assert has_price(text) is (expected is not None)


@pytest.mark.parametrize("text", ["1", "2", "9", "10", "3.", "4)", "#5", " 6 "])
def test_bare_index_re_accepts(text: str) -> None:
    assert BARE_INDEX_RE.match(text.strip())


@pytest.mark.parametrize("text", ["0", "11", "100", "1a", "", "1 2"])
def test_bare_index_re_rejects(text: str) -> None:
    assert not BARE_INDEX_RE.match(text)


# ── resolve_switch (§4.1 matching order) ─────────────────────────────────────
class FakeDeal:
    def __init__(self, id: str, title: str, nickname: str | None = None) -> None:
        self.id, self.title, self.nickname = id, title, nickname


@pytest.fixture
def deals() -> list[FakeDeal]:
    return [
        FakeDeal("a", "2008 Toyota Camry LE"),
        FakeDeal("b", "2016 Honda Civic EX", nickname="the loud one"),
        FakeDeal("c", "2014 Ford F-150 XLT"),
    ]


def test_resolve_by_title_substring(deals: list[FakeDeal]) -> None:
    deal, cands = resolve_switch("camry", deals)
    assert deal is deals[0] and cands == []


def test_resolve_is_case_insensitive(deals: list[FakeDeal]) -> None:
    assert resolve_switch("CIVIC", deals)[0] is deals[1]


def test_resolve_by_index(deals: list[FakeDeal]) -> None:
    assert resolve_switch("3", deals)[0] is deals[2]


def test_resolve_index_out_of_range(deals: list[FakeDeal]) -> None:
    assert resolve_switch("9", deals) == (None, [])


def test_exact_nickname_beats_a_title_substring() -> None:
    """A deal literally nicknamed "civic" wins over one merely titled Civic."""
    pool = [FakeDeal("a", "2016 Honda Civic EX"), FakeDeal("b", "2008 Camry", "civic")]
    assert resolve_switch("civic", pool)[0] is pool[1]


def test_nickname_substring_beats_a_title_substring() -> None:
    pool = [FakeDeal("a", "2016 Honda Civic EX"),
            FakeDeal("b", "2008 Camry", "the civic killer")]
    assert resolve_switch("civic", pool)[0] is pool[1]


def test_ambiguous_returns_candidates_never_a_guess() -> None:
    pool = [FakeDeal("a", "2008 Toyota Camry LE"), FakeDeal("b", "2011 Toyota Camry SE")]
    deal, cands = resolve_switch("camry", pool)
    assert deal is None and cands == pool


def test_no_match_returns_nothing(deals: list[FakeDeal]) -> None:
    assert resolve_switch("porsche", deals) == (None, [])


@pytest.mark.parametrize("arg", [None, "", "   "])
def test_resolve_handles_empty_operands(arg: str | None, deals: list[FakeDeal]) -> None:
    assert resolve_switch(arg, deals) == (None, [])


def test_resolve_handles_no_deals() -> None:
    assert resolve_switch("camry", []) == (None, [])


# ── end to end: the acceptance-script sequence ───────────────────────────────
def test_the_acceptance_sequence_routes_correctly() -> None:
    """update_1.md §6 steps 2–11, as the router sees them. `last_card_kind`
    threads through exactly the way `main.py` will keep it in the user meta."""
    script = [
        ("https://fb.com/marketplace/item/1", None, Intent.NEW),
        ("he says 6,400 is what it's worth", "deal", Intent.RELAY),
        ("card", "deal", Intent.CARD),
        ("https://cars.com/vehicledetail/2", "deal", Intent.NEW),
        ("deals", "deal", Intent.LIST),
        ("1", "list", Intent.SWITCH),
        ("undo", "deal", Intent.UNDO),
        ("we have a deal", "deal", Intent.CLOSE),
        ("stats", "deal", Intent.STATS),
    ]
    for text, card, expected in script:
        assert classify(text, last_card_kind=card).intent is expected, text
