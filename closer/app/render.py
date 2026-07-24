"""PNG cards — the belief curve as a real image in an iMessage bubble (§4.6).

The Unicode card in `cards.py` ships first and is never blocked on this module.
This is the upgrade that lands on top: the seller's floor estimate collapsing
turn by turn, with the turn it refused to move called out by an arrow. That
picture is the pitch.

    deal_png(deal)   -> bytes   1200x900 PNG, the belief curve
    stats_png(deals) -> bytes   1200x900 PNG, lifetime savings

Three rules this module holds to:

**Never raise.** A chart is decoration on a message that must arrive. Every
entry point degrades — no research, no snapshot, no turns, a single turn, a
missing `floor_std` — and the caller always gets valid PNG bytes back.

**No pyplot.** `_process_inbound` runs on a worker thread and pyplot keeps
global figure state that is not thread-safe. `Figure` + `FigureCanvasAgg`
directly has no global state, so two users can render at the same time.

**No emoji.** matplotlib's bundled DejaVu Sans has no emoji coverage and
substitutes an empty box, which looks like a bug on a projector. The Unicode
cards carry the emoji; the PNG carries the geometry.

Palette is the existing product palette (`#0b0e14` ground, `#5b8cff` accent) so
the card, the fallback slide and the thread all read as one product.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional, Sequence

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

from . import cards

if TYPE_CHECKING:                                  # avoid an import cycle at runtime
    from .state import Deal

matplotlib.use("Agg")

# Every label on this chart is a dollar amount, and matplotlib treats `$…$` as
# mathtext by default — "listed $6,400 · they're at $5,400" renders as italic
# math with the dollar signs eaten. Off globally rather than escaped at each
# call site, because the failure is silent and every new label would inherit it.
matplotlib.rcParams["text.parse_math"] = False

# ── palette ──────────────────────────────────────────────────────────────────
BG = "#0b0e14"          # page ground, shared with the fallback slide
PANEL = "#131823"       # footer band + annotation boxes
GRID = "#1e2534"
INK = "#e6e9ef"         # primary text
MUTED = "#8892a6"       # labels, axis text
ACCENT = "#5b8cff"      # the floor estimate — the hero line
BAND = "#5b8cff"        # its ±1σ uncertainty
SELLER = "#ffb454"      # what they are asking, descending
OURS = "#7bd88f"        # what we offered, ascending
GOOD = "#35d07f"        # fair value V
DANGER = "#ff6b6b"      # walk-away R
BLUFF = "#ff7ac6"       # the callout

WIDTH_PX, HEIGHT_PX, DPI = 1200, 900, 100
FIGSIZE = (WIDTH_PX / DPI, HEIGHT_PX / DPI)

FONT = "DejaVu Sans"    # bundled with matplotlib, so it renders on any machine


def _money(n: Optional[float]) -> str:
    return f"${n:,.0f}" if n is not None else "—"


def _ellipsis(text: str, limit: int) -> str:
    """Trim at a word boundary. Deal titles are `2014 Ford F-150 XLT SuperCrew`
    often enough that a hard slice cuts mid-word."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return (t[:limit].rsplit(" ", 1)[0] or t[:limit]).rstrip(" ,-") + "…"


def _figure() -> Figure:
    fig = Figure(figsize=FIGSIZE, dpi=DPI, facecolor=BG)
    FigureCanvasAgg(fig)
    return fig


def _to_png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=DPI)
    return buf.getvalue()


def _header(fig: Figure, title: str, subtitle: str) -> None:
    fig.text(0.055, 0.945, title, color=INK, fontsize=30, fontweight="bold",
             fontfamily=FONT, va="center")
    fig.text(0.055, 0.895, subtitle, color=MUTED, fontsize=16,
             fontfamily=FONT, va="center")
    # A hairline under the header does the work a box would, without the weight.
    fig.add_artist(matplotlib.lines.Line2D([0.055, 0.945], [0.868, 0.868],
                                           color=GRID, linewidth=1.4))


def _footer_band(fig: Figure, rect: tuple[float, float, float, float]) -> None:
    x, y, w, h = rect
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                  transform=fig.transFigure, facecolor=PANEL,
                                  edgecolor=GRID, linewidth=1.2, zorder=0))


def _style_axes(ax) -> None:
    ax.set_facecolor(BG)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(1.2)
    ax.tick_params(colors=MUTED, labelsize=13, length=4)
    ax.grid(True, color=GRID, linewidth=0.9, alpha=0.7)
    ax.set_axisbelow(True)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT)


def _placeholder(title: str, subtitle: str, lines: Sequence[tuple[str, str]],
                 note: str) -> bytes:
    """The card for a deal with no curve yet — researching, or link-only.

    A judge sees this in the first thirty seconds, so it is a designed state and
    not an error page: the same header, the same palette, the numbers we do have
    laid out as a key/value stack.
    """
    fig = _figure()
    _header(fig, title, subtitle)
    y = 0.72
    for label, value in lines:
        fig.text(0.055, y, label, color=MUTED, fontsize=18, fontfamily=FONT, va="center")
        fig.text(0.945, y, value, color=INK, fontsize=26, fontweight="bold",
                 fontfamily=FONT, va="center", ha="right")
        fig.add_artist(matplotlib.lines.Line2D([0.055, 0.945], [y - 0.055, y - 0.055],
                                               color=GRID, linewidth=1))
        y -= 0.13
    fig.text(0.055, max(y - 0.02, 0.08), note, color=MUTED, fontsize=17,
             fontfamily=FONT, va="center", wrap=True)
    return _to_png(fig)


# ── the deal card ────────────────────────────────────────────────────────────
def _reference_lines(ax, deal: "Deal") -> None:
    """Horizontal lines at asking / V / R, labelled at the right edge.

    Labels are nudged apart when two references land within a few pixels of each
    other — on a tight deal `V` and the last seller price can be $80 apart, and
    two overlapping labels read as one corrupted one.
    """
    refs = [(deal.asking, MUTED, "asking"),
            (deal.V, GOOD, "fair value"),
            (deal.R, DANGER, "walk-away")]
    refs = [(float(v), c, t) for v, c, t in refs if v is not None]
    if not refs:
        return
    for value, color, _ in refs:
        ax.axhline(value, color=color, linewidth=1.6, linestyle=(0, (6, 5)), alpha=0.85)

    lo, hi = ax.get_ylim()
    span = (hi - lo) or 1.0
    gap = 0.055 * span                              # min vertical spacing in data units
    placed: list[float] = []
    for value, color, text in sorted(refs, key=lambda r: r[0]):
        y = value
        for taken in placed:
            if abs(y - taken) < gap:
                y = taken + gap
        placed.append(y)
        ax.annotate(f"{text} {_money(value)}",
                    xy=(1.0, y), xycoords=("axes fraction", "data"),
                    xytext=(8, 0), textcoords="offset points",
                    color=color, fontsize=13, fontfamily=FONT, va="center",
                    annotation_clip=False)


def _bluff_callout(ax, deal: "Deal", traj: list[dict], turns: list[int],
                   floors: list[float]) -> None:
    """The arrow that makes the point. Drawn only when `cards.bluff_turn` says so.

    Anchored to the floor estimate on the qualifying turn and thrown upward,
    because the space above the floor line is where the seller's own prices sit
    and the visual contrast — their number high, our estimate flat — is the
    argument.
    """
    found = cards.bluff_turn(deal, traj)
    if found is None:
        return
    turn, delta = found
    n = turn.get("turn")
    if n not in turns:
        return
    y = floors[turns.index(n)]
    lo, hi = ax.get_ylim()
    span = (hi - lo) or 1.0
    quote = cards._quote(turn.get("seller_text"), limit=44)
    moved = "didn't move" if delta < 1 else f"moved {_money(delta)}"
    label = f'Turn {n}: "{quote}"\nthe curve {moved}' if quote \
        else f"Turn {n}: the pressure play\nthe curve {moved}"
    ax.annotate(
        label,
        xy=(n, y), xytext=(n, y + 0.34 * span),
        color=BLUFF, fontsize=14, fontfamily=FONT, ha="center", va="bottom",
        bbox=dict(boxstyle="round,pad=0.55", facecolor=PANEL, edgecolor=BLUFF,
                  linewidth=1.4, alpha=0.96),
        arrowprops=dict(arrowstyle="-|>", color=BLUFF, linewidth=2,
                        shrinkA=6, shrinkB=8,
                        connectionstyle="arc3,rad=0.0"),
        annotation_clip=False, zorder=12)


def _recommendation_footer(fig, deal: "Deal", traj: list[dict]) -> None:
    """`Send $4,750 · 68% they take it`, plus confidence and the zone.

    Reads the persisted snapshot rather than recomputing: the snapshot is what
    the thread already told the user, and a card that disagrees with the message
    above it is worse than no card.
    """
    snap = deal.snapshot or {}
    # Top edge at 0.195 leaves clearance for the legend, which hangs below the
    # axes at ~0.215. They collided at the original height and the legend read
    # as a stray row inside the recommendation panel.
    _footer_band(fig, (0.055, 0.040, 0.89, 0.155))

    action = (snap.get("action") or "").upper()
    offer = snap.get("offer")
    verb = {"COUNTER": "Send", "ACCEPT": "Take it at", "HOLD": "Hold at",
            "WALK": "Walk — their floor is above"}.get(action, "Next move")
    headline = f"{verb} {_money(offer)}" if offer is not None else "Waiting on their next move"
    fig.text(0.085, 0.145, headline, color=INK, fontsize=27, fontweight="bold",
             fontfamily=FONT, va="center")

    p = snap.get("p_accept")
    if p is not None:
        fig.text(0.085, 0.093, f"{float(p):.0%} they take it", color=ACCENT,
                 fontsize=18, fontfamily=FONT, va="center")

    std = snap.get("floor_std")
    dots = cards.confidence_dots(std, deal.asking)
    conf = cards.meter(dots)
    tail = f"  (±{_money(std)})" if std is not None else ""
    fig.text(0.915, 0.145, f"confidence {conf}{tail}", color=MUTED, fontsize=16,
             fontfamily=FONT, va="center", ha="right")

    # The zone runs from the posterior's low end to OUR ceiling, not to
    # `zopa_high` — `cards.py:391` is the contract and a card that disagrees
    # with the message above it is worse than no card. When the floor reads
    # above the ceiling there is no zone, and saying so is the useful line.
    low, ceiling = snap.get("zopa_low"), snap.get("ceiling")
    if low is not None and ceiling is not None:
        zone = (f"zone of agreement {_money(low)}–{_money(ceiling)}"
                if low <= ceiling else
                f"no zone — their floor reads above your {_money(ceiling)} ceiling")
        fig.text(0.915, 0.093, zone, color=MUTED, fontsize=16,
                 fontfamily=FONT, va="center", ha="right")

    fig.text(0.085, 0.058, f"turn {len(traj)} · Closer", color=MUTED, fontsize=13,
             fontfamily=FONT, va="center")


def _deal_png(deal: "Deal") -> bytes:
    traj = cards._trajectory(deal)
    points = [(int(t["turn"]), float(t["floor_est"])) for t in traj
              if t.get("turn") is not None and t.get("floor_est") is not None]

    name = cards._name(deal)
    if not points:
        # No curve yet. Show what research did find, or say plainly that it is
        # still running — both are real states, neither is an error.
        rows = [("listed", _money(deal.asking)),
                ("fair value", _money(deal.V)),
                ("walk-away", _money(deal.R))]
        state = cards._state(deal)
        note = ("Send me the listing link and I'll come back with what it's "
                "actually worth." if state == "AWAITING_LINK" else
                "Comps and known problems, then a number. The curve starts on "
                "their first reply.")
        return _placeholder(name, _subtitle(deal, traj), rows, note)

    turns = [p[0] for p in points]
    floors = [p[1] for p in points]
    stds = [t.get("floor_std") for t in traj
            if t.get("turn") is not None and t.get("floor_est") is not None]

    fig = _figure()
    _header(fig, name, _subtitle(deal, traj))
    # The right margin is not whitespace — `_reference_lines` writes "asking
    # $6,400" / "fair value" / "walk-away" into it. Sized so the longest of the
    # three fits rather than being clipped at the figure edge.
    ax = fig.add_axes((0.075, 0.315, 0.700, 0.515))
    _style_axes(ax)

    # ±1σ band first, so the line and the markers sit on top of it.
    if any(s is not None for s in stds):
        filled = [float(s) if s is not None else 0.0 for s in stds]
        ax.fill_between(turns,
                        [f - s for f, s in zip(floors, filled)],
                        [f + s for f, s in zip(floors, filled)],
                        color=BAND, alpha=0.16, linewidth=0, zorder=2)

    ax.plot(turns, floors, color=ACCENT, linewidth=3.2, marker="o", markersize=9,
            markerfacecolor=BG, markeredgewidth=2.6, markeredgecolor=ACCENT,
            zorder=6, label="their floor, as we read it")

    _series(ax, traj, "seller_price", SELLER, "v", "what they're asking")
    _series(ax, traj, "our_offer", OURS, "^", "what we offered")

    ax.set_xticks(turns)
    ax.set_xticklabels([str(t) for t in turns])
    ax.set_xlabel("turn", color=MUTED, fontsize=14, fontfamily=FONT, labelpad=10)
    ax.set_xlim(min(turns) - 0.45, max(turns) + 0.45)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"${v:,.0f}")

    _pad_ylim(ax, deal, floors, stds, traj)
    _reference_lines(ax, deal)
    _bluff_callout(ax, deal, traj, turns, floors)

    # Below the axes, laid out horizontally. Inside the plot it covered the
    # opening turns — which on a converging negotiation is exactly where the
    # interesting spread is.
    legend = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.135), ncols=3,
                       frameon=False, fontsize=14, labelcolor=INK,
                       handlelength=2.2, columnspacing=2.4)
    for text in legend.get_texts():
        text.set_fontfamily(FONT)

    _recommendation_footer(fig, deal, traj)
    return _to_png(fig)


def _series(ax, traj: list[dict], key: str, color: str, marker: str,
            label: str) -> None:
    """One secondary series — their prices or ours — as markers on a faint line.

    Gaps are real: a turn where the seller restated a position without naming a
    number has no price, and connecting across it would draw a concession that
    never happened. So gaps break the line rather than being interpolated.
    """
    pts = [(int(t["turn"]), float(t[key])) for t in traj
           if t.get("turn") is not None and t.get(key) is not None]
    if not pts:
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    ax.plot(xs, ys, color=color, linewidth=1.6, alpha=0.55,
            linestyle=(0, (5, 4)), zorder=4)
    ax.plot(xs, ys, color=color, linestyle="none", marker=marker, markersize=11,
            markeredgewidth=0, zorder=5, label=label)


def _pad_ylim(ax, deal: "Deal", floors: list[float], stds: list[Optional[float]],
              traj: list[dict]) -> None:
    """Fit every series AND every reference line, then leave room for the callout.

    The bluff annotation is thrown a third of the range above the floor line, so
    the range has to be tall enough to hold it — otherwise the one label the
    whole card exists for is clipped off the top.
    """
    values = list(floors)
    for f, s in zip(floors, stds):
        if s is not None:
            values += [f - float(s), f + float(s)]
    for t in traj:
        for key in ("seller_price", "our_offer"):
            if t.get(key) is not None:
                values.append(float(t[key]))
    for ref in (deal.asking, deal.V, deal.R):
        if ref is not None:
            values.append(float(ref))
    lo, hi = min(values), max(values)
    span = (hi - lo) or max(abs(hi), 1.0) * 0.1
    ax.set_ylim(lo - 0.10 * span, hi + 0.30 * span)


def _subtitle(deal: "Deal", traj: list[dict]) -> str:
    bits = []
    if deal.asking is not None:
        bits.append(f"listed {_money(deal.asking)}")
    if deal.last_seller_price is not None:
        bits.append(f"they're at {_money(deal.last_seller_price)}")
    state = cards._state(deal)
    if state == "CLOSED":
        bits.append(f"closed at {_money(cards._closed_price(deal))}")
    elif state == "WALKED":
        bits.append("walked")
    elif traj:
        bits.append(f"turn {len(traj)}")
    elif state == "AWAITING_RESEARCH":
        bits.append("researching")
    return "  ·  ".join(bits) or "no numbers yet"


def deal_png(deal: "Deal") -> bytes:
    """The belief curve as a 1200x900 PNG. Never raises — see the module docstring."""
    try:
        return _deal_png(deal)
    except Exception as exc:                          # noqa: BLE001 — decoration
        return _placeholder(cards._name(deal), "chart unavailable", [],
                            f"The numbers are in the message above. ({type(exc).__name__})")


# ── the stats card ───────────────────────────────────────────────────────────
def _stats_png(deals: Sequence["Deal"]) -> bytes:
    saved = [(cards._name(d), float(cards._saved(d) or 0.0)) for d in deals
             if cards._state(d) == "CLOSED" and cards._saved(d) is not None]
    total = sum(v for _, v in saved)
    closed = len(saved)
    live = sum(1 for d in deals if d.is_active())
    walked = sum(1 for d in deals if cards._state(d) == "WALKED")
    minutes = cards._minutes(deals)

    subtitle = f"{closed} closed  ·  {live} live  ·  {len(deals)} deals total"
    if walked:
        subtitle += f"  ·  walked {walked}"

    if not saved:
        rows = [("deals", str(len(deals))), ("live", str(live)),
                ("walked", str(walked))]
        return _placeholder("Closer, all time", subtitle, rows,
                            "Nothing closed yet. Close one and this becomes a "
                            "number you can point at.")

    fig = _figure()
    _header(fig, "Closer, all time", subtitle)

    fig.text(0.055, 0.775, _money(total), color=GOOD, fontsize=58,
             fontweight="bold", fontfamily=FONT, va="center")
    fig.text(0.055, 0.700, f"saved across {closed} closed deal"
                           f"{'s' if closed != 1 else ''}",
             color=MUTED, fontsize=19, fontfamily=FONT, va="center")
    if minutes:
        fig.text(0.945, 0.775, f"{minutes:.0f} min", color=INK, fontsize=34,
                 fontweight="bold", fontfamily=FONT, va="center", ha="right")
        fig.text(0.945, 0.700, "spent texting me", color=MUTED, fontsize=17,
                 fontfamily=FONT, va="center", ha="right")

    # Bars ascending so the personal best is the top bar — the one the eye lands
    # on, and the one `fireworks` fires for (§5.4).
    saved.sort(key=lambda r: r[1])

    # Height tracks the row count instead of filling the panel. A fixed-height
    # axes with one closed deal renders that deal as a slab covering half the
    # card, which reads as a rendering fault rather than as one bar. The left
    # margin is reserved for the deal names — they are y tick labels and get
    # clipped at the figure edge otherwise.
    rows = len(saved)
    height = min(0.44, 0.085 * rows + 0.045)
    # Centred in the space below the headline rather than hung from its top, so
    # a one-deal card is a small chart in the middle and not a small chart with
    # half a page of dead ground under it.
    ax = fig.add_axes((0.285, 0.10 + (0.52 - height) / 2, 0.60, height))
    _style_axes(ax)
    ax.grid(True, axis="x", color=GRID, linewidth=0.9, alpha=0.7)
    ax.grid(False, axis="y")

    ys = range(rows)
    best = max(v for _, v in saved)
    colors = [GOOD if v == best else ACCENT for _, v in saved]
    ax.barh(list(ys), [v for _, v in saved], color=colors, height=0.6, zorder=3)
    ax.set_ylim(-0.62, rows - 0.38)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([_ellipsis(n, 24) for n, _ in saved], color=INK,
                       fontsize=15, fontfamily=FONT)
    ax.xaxis.set_major_formatter(lambda v, _pos: f"${v:,.0f}")
    ax.set_xlim(0, best * 1.18)
    for y, (_, v) in zip(ys, saved):
        ax.text(v + best * 0.02, y, _money(v), color=INK, fontsize=15,
                fontfamily=FONT, va="center", fontweight="bold")
    return _to_png(fig)


def stats_png(deals: Sequence["Deal"]) -> bytes:
    """Lifetime savings as a 1200x900 PNG. Never raises."""
    try:
        return _stats_png(list(deals))
    except Exception as exc:                          # noqa: BLE001 — decoration
        return _placeholder("Closer, all time", "chart unavailable", [],
                            f"The numbers are in the message above. ({type(exc).__name__})")


__all__ = ["deal_png", "stats_png", "WIDTH_PX", "HEIGHT_PX"]


# ── python -m app.render --demo ──────────────────────────────────────────────
if __name__ == "__main__":                          # pragma: no cover
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    if "--demo" not in args:
        print("usage: python -m app.render --demo [--out DIR] [--send +1XXXXXXXXXX]\n"
              "\n"
              "  --demo   render every PNG card from the committed fixtures,\n"
              "           including the null states\n"
              "  --out    where to write them (default ./render-demo)\n"
              "  --send   also send them to a number, so the chart can be checked\n"
              "           in a real iMessage bubble rather than an image viewer")
        raise SystemExit(2)

    out = Path(args[args.index("--out") + 1] if "--out" in args else "render-demo")
    out.mkdir(parents=True, exist_ok=True)
    demo_deals = cards._demo_deals()

    written: list[tuple[str, Path]] = []
    for deal in demo_deals:
        path = out / f"deal_{cards._state(deal).lower()}_{deal.id[:6]}.png"
        path.write_bytes(deal_png(deal))
        written.append((f"deal_png · {cards._name(deal)} · {cards._state(deal)}", path))
    for label, pool in (("stats_png", demo_deals), ("stats_png · empty", [])):
        path = out / f"{label.replace(' · ', '_').replace(' ', '')}.png"
        path.write_bytes(stats_png(pool))
        written.append((label, path))

    for label, path in written:
        print(f"{label:<52} {path}  ({path.stat().st_size:,} bytes)")

    if "--send" in args:
        import time

        from . import linq
        to = args[args.index("--send") + 1]
        if not linq.available():
            raise SystemExit("LINQ_API_KEY is not set — nothing to send with.")
        for label, path in written:
            linq.send_media(to, label, str(path))
            print(f"sent {label} → {to}")
            time.sleep(0.8)
