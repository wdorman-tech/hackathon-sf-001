# Closer — Design System

Brand identity + UI design system for **Closer** (the AI negotiation coach that lives in
iMessage). Originally adopted from the visual language of the **BidPilot dashboard**
(`/Users/arshawnarbabi/Downloads/BidPilot/bidpilot-dashboard`), then converted to a dark theme
per direct request — see §1 and the Decisions log. This document is the source of truth for
tokens, type, spacing, components, motion, and voice — write no landing-page code against
anything *not* in here without updating this file first.

Status: **the landing page is built and running** (`web/`, Vite + React + TS). See §11 for
what shipped and §12 for the full decisions log.

---

## 0. Where this came from

Read in full before writing a single token: BidPilot's `app/globals.css`, `app/layout.tsx`,
`app/page.tsx`, `app/login/page.tsx`, `components/ui/{button,card,badge}.tsx`, `lib/utils.ts`,
`package.json`, `components.json`, and its logo SVG — plus Closer's own `closer/README.md`,
`CLOSER_BUILD_PROMPT.md`, `closer/static/dashboard.html`, the root
`negotiation-dashboard-mockup.html`, and the actual `closer/app/*.py` backend (engine, research,
llm, state machine) for product facts.

Two more source projects got pulled in mid-build, both Arshawn's own prior work, per direct
request — see §13:
- `/Users/arshawnarbabi/Downloads/Temperance/Temperance_Website/public/phone_mockup.png` — the
  phone bezel used in the hero.
- `/Users/arshawnarbabi/Downloads/Temperance/Temperance_Website/lib/liquidGlass.ts` — the real
  SVG-refraction "liquid glass" engine used in the nav.

Nothing here is invented — every color, font, and spacing value is either lifted verbatim from
a real source or extended from it using that source's own math (e.g. BidPilot's own
`--radius ± Npx` pattern).

Confirmed detail worth keeping on file: BidPilot's own primary token `hsl(164 100% 28%)` is
**exactly** `#008F68`, the accent color baked into BidPilot's own logo SVG — that was the
anchor color for the *light* system this all started from. Closer's own primary (below) is a
deliberately different hue, chosen directly rather than inherited.

---

## 1. Color — dark theme

**The site is dark, not light.** BidPilot's own dashboard is light; Closer's landing page
converted to a dark theme per direct request mid-build. What's kept from BidPilot is the
*system* — the same hue families, the same relationships between a token and its foreground,
the same hairline-border/no-shadow restraint — just flipped from a light surface to a dark one,
the same way you'd tune a dark-mode variant of any real design system.

### 1.1 Core tokens (HSL custom properties)

| Token | HSL | Hex (≈) | Use |
|---|---|---|---|
| `--background` | `0 0% 7%` | `#121212` | page canvas — **neutral grayscale, zero saturation**, no blue/navy tint (an earlier `224° 24%` navy-black was corrected per direct feedback: "full neutral black scale, no bluish tint") |
| `--foreground` | `0 0% 96%` | `#F5F5F5` | primary text/ink |
| `--card` / `--popover` | `0 0% 10%` | `#1A1A1A` | elevated surface — a hair lighter than the page for card separation without a shadow |
| `--card-foreground` / `--popover-foreground` | same as `--foreground` | | |
| `--primary` | `100 100% 50%` | `#55FF00` | **Closer's brand color** — a saturated lime-green, bright enough to read as text/icon color on a dark surface (see §1.1.1 for the full hue history) — CTAs, links, active states |
| `--primary-foreground` | `0 0% 7%` | `#121212` | text *on* a primary-colored button — dark ink on the bright green |
| `--secondary` / `--muted` | `0 0% 15%` | `#262626` | quiet fills, secondary buttons |
| `--secondary-foreground` | `0 0% 92%` | | |
| `--muted-foreground` | `0 0% 65%` | `#A6A6A6` | secondary/help text |
| `--accent` | `100 100% 14%` | `#184700` | dark-tinted surface for icon chips |
| `--accent-foreground` | `100 100% 60%` | `#77FF33` | icon/text color on the accent surface — brighter than `--primary` on purpose, a small pop against a colored chip |
| `--destructive` | `0 72% 58%` | `#E14747` | errors, WALK state |
| `--border` / `--input` | `0 0% 20%` | `#333333` | hairline borders |
| `--ring` | same as `--primary` | | focus ring |
| `--radius` | `0rem` | `0px` | **the whole radius scale is zero — see §4, "sharp and geometric" is the current direction, not a legacy BidPilot value.** |

Contrast checked, not assumed: foreground-on-background ≈ 17.9:1, primary-on-background ≈
14.9:1 — comfortably AA/AAA for body text.

#### 1.1.1 On the brand color specifically

The full hue history, in the order it actually happened (every step was a live, in-browser
correction, not a first-guess-right pick):

1. Arshawn chose `#00734D` directly as Closer's own color at `160.2°` (distinct from BidPilot's
   `164°` teal, on purpose).
2. Converting to dark theme meant that exact hex, at `22.5%` lightness, was no longer legible as
   text/icon color against a near-black background — lifted to the same hue at `70%/50%`
   (`#26D99E`).
3. A same-hue desaturated pass (aiming for "calmer") read as **"muddier"** instead — reverted.
   Lesson: muting a color by dropping saturation/lightness together reads as dirty, not
   sophisticated; shifting hue at constant S/L is what actually changes character.
4. Hue moved `160.2°` ("too mint") → `140°` ("too green") → settled at `150°` (`#2CDD85`).
5. A completely different direction: **`#B8FF00`**, an exact hex handed over directly — a bright
   yellow-lime at `76.7°`, `100%/50%`. Read as "too yellow."
6. Hue nudged down to **`100°`**, same `100%/50%` — **`#55FF00`**, the current value. Full
   saturation and lightness kept at every step from #5 onward; only the hue moved.

The `#00734D`-family dark fills didn't disappear even after the hue-100 pivot — recomputed at
each new hue as a legible-on-white-text dark fill (`#007339` at `150°`, then `#4C650B` at
`100°/80%/22%`), they're still exactly right for contexts where light text sits *on top* of the
color (the phone screen's outgoing chat bubbles, the nav's unused `tintColor`, the printable
card's accent — §13, §7).

**Border weight is a deliberate BidPilot signature, kept as-is: `0.3px`, not `1px`.** A
near-invisible hairline instead of a standard rule is one of the details that keeps this reading
as premium instead of template-y, light or dark:
```css
.border   { border-width: 0.3px; }
.border-t { border-top-width: 0.3px; }
```

### 1.2 Extended tokens

| Token | Value | Use |
|---|---|---|
| `--paper` | `hsl(224 22% 9%)` ≈ `#12151C` | alternate section band — a hair lighter than `--background`, banding by feel not contrast, same idea as the light system's `--paper` |
| `--hairline` | `hsl(222 18% 18%)` ≈ `#262B36` | slightly lighter divider for nested/quiet lines |

### 1.3 Status / semantic colors

BidPilot's own convention — reach for stock Tailwind hues rather than inventing custom status
colors — carries over, but the light-mode pastel pairing (`bg-blue-100 text-blue-700`) reads as
a jarring light patch on a dark page. The dark-appropriate equivalent is a low-opacity tinted
fill with a light-toned text color instead:

| Action | Badge classes (dark) | Light-mode equivalent (for reference) |
|---|---|---|
| **COUNTER** | `bg-blue-400/15 text-blue-300` | `bg-blue-100 text-blue-700` |
| **HOLD** (bluff called) | `bg-amber-400/15 text-amber-300` | `bg-amber-100 text-amber-700` |
| **CLOSED / ACCEPT** | `bg-emerald-400/15 text-emerald-300` | `bg-emerald-100 text-emerald-700` |
| **WALK** | `bg-destructive/15 text-red-300` | `bg-red-100 text-red-600` |
| idle / neutral | `bg-secondary text-secondary-foreground` | `bg-gray-100 text-gray-500` |

Still directionally consistent with the color logic in `negotiation-dashboard-mockup.html`
(green=go/closed, amber=hold/bluff, red=walk, blue=counter) — same semantics, dark-appropriate
opacity instead of light pastel.

### 1.4 The *other* dark panel — `negotiation-dashboard-mockup.html`'s own tokens

Kept on file, separately namespaced, purely for reference — **not used anywhere on the current
site** and not touched (decisions log). This is a different dark palette than §1.1 above; if a
future session ever embeds that widget as-is, use its own values verbatim rather than the
site's `--background`/`--card`/etc.:

```css
--panel-bg:     #070a10;
--panel-surface:#0f151e;
--panel-raise:  #182231;
--panel-border: #212c3b;
--panel-ink:    #eaf1f8;
--panel-muted:  #8592a2;
--panel-go:     #3fd07a;
--panel-amber:  #e3b341;
--panel-red:    #f16f6f;
--panel-cyan:   #5cb3ff;
```

**Deliberate light-mode exception:** the standalone printable contact card
(`public/print-cards.html`) stays light, on purpose — dark backgrounds waste ink/toner and look
bad printed on white paper. It's not part of the scrolling site and isn't bound by §1's dark
tokens.

---

## 2. Typography

### 2.1 Family

**DM Sans** for everything — headings and body alike. Self-hosted via
`@fontsource-variable/dm-sans` (not `next/font`, since the app is Vite, not Next — see §11),
imported once in `src/index.css`, exposed as `--font-dm-sans`.

For **numerals only** (dollar figures, percentages, belief-curve stats) — a monospace accent:
`ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`, `font-variant-numeric:
tabular-nums`, via a `.money` utility class. Inherited from Closer's *own* existing dashboard
mockups, which already render every dollar amount in mono. **Numbers are always mono, tabular,
everywhere on the site** — a small detail that reads as "the math is real."

### 2.2 Type scale

| Role | Size | Line-height | Tracking | Weight |
|---|---|---|---|---|
| Eyebrow / kicker | `11px` | 1 | `0.14em`, uppercase | 600 |
| Caption / micro | `12px` | 1.4 | normal | 500 |
| Body small | `14px` | 1.55 | normal | 400 |
| Body base (marketing copy) | `16–17px` | 1.6 | normal | 400 |
| Body large / lede | `18–20px` | 1.5 | `-0.005em` | 400–500 |
| H3 / card head | `20–24px` | 1.25 | `-0.01em` | 600 |
| H2 / section head | `clamp(28px, 4vw, 40px)` | 1.1 | `-0.02em` | 700 |
| H1 / hero display | `clamp(52px, 8vw, 76px)` | 1.02 | `-0.03em` | 700 |
| Stat / numeral display | `28–56px` (context-dependent) | 1 | `-0.01em` | 600–700, mono |

The hero H1 landed at the top of this range in practice ("Know what to send. Call the bluff." —
see §10) — short, two-clause, set large.

---

## 3. Spacing

Base unit: **4px**, Tailwind's default scale — no custom scale needed, just usage rhythm:

- **Component padding:** `12–24px`
- **Grid/card gutters:** `12–24px`
- **Marketing section rhythm:** `py-24` to `py-40` (96–160px) between major sections — a
  dashboard is dense by necessity, a landing page has to breathe.
- **Container width:** `1200–1280px` for text/content columns.

---

## 4. Radius — sharp, geometric, zero

**Superseded direction, kept only as history:** this section originally documented BidPilot's
`--radius: 0.75rem` shadcn scale (soft rounded-2xl cards, pill buttons and nav). Per direct
request ("make all edges in the home page sharp and geometric") the entire scale was zeroed and
every hardcoded `rounded-full` / `rounded-2xl` / `rounded-[...]` instance across every component
was swept out by hand — buttons, cards, badges, the nav pill (now a sharp rectangle), the CTA
band, the QR contact cards, even small circular elements like the timeline dot markers (§ Proof)
and the "live" pulse indicator are now squares, not circles.

```css
--radius-sm: 0px; --radius-md: 0px; --radius-lg: 0px;
--radius-xl: 0px; --radius-2xl: 0px; --radius-3xl: 0px;
```

Zeroing the token scale alone only catches components that reference `rounded-xl`/`rounded-2xl`
(Card, Button, the icon chips in HowItWorks/Engine/Trust — those needed no per-file edit). It
does **not** catch `rounded-full` (Tailwind's "fully rounded" utility is always `9999px`,
independent of the radius theme scale) or any arbitrary `rounded-[...]` value — those had to be
found and removed file-by-file.

**One deliberate exception:** `src/components/Phone.tsx`'s `SCREEN_INSET.borderRadius: "9% /
4.4%"`. That's not a design choice — it's matching the *real, physically rounded* screen corner
baked into the `phone-mockup.png` photo itself. Squaring it off would make the screen content
visibly poke past the phone's actual glass edge in the image, reading as a rendering bug rather
than a style. The phone bezel is the one place "sharp everywhere" yields to "matches the real
object."

---

## 5. Elevation & borders

BidPilot's real signature: **almost no box-shadow**, hairline border instead. On a dark theme
this becomes: flat elevated `--card` surface + `0.3px` `--border` line at rest, no shadow.

- **Resting state:** hairline border only, no shadow.
- **Hover / lift:** a single soft, large-blur, low-opacity ambient shadow, never a hard drop
  shadow — e.g. `0 20px 50px -20px rgba(0,0,0,0.5)`.
- **The floating nav** doesn't use a manual shadow or border at all — no CSS `border`, and
  `edgeHighlight` (the glass engine's specular rim-highlight `box-shadow`, §13.2) is set to `0`
  per direct feedback ("no stroke"). Its only elevation cue is `shadowBlur`/`shadowOpacity`, and
  it's now a sharp rectangle, not a pill (§4).

**No decorative color gradients, anywhere** — this was a direct correction mid-build (the hero
originally had a blurred radial-glow blob, the CTA band had a `radial-gradient` sheen overlay;
both were removed). The one exception is a `mask-image: linear-gradient(...)` on the hero's dot
canvas (§9.1) — that's an invisible alpha mask controlling *where dots fade out*, not a visible
color gradient, so it doesn't violate the rule in spirit.

---

## 6. Iconography

**Hugeicons** (`@hugeicons/react` + `@hugeicons/core-free-icons`), matching BidPilot's actual
practice, `strokeWidth={1.5}`, ~14–18px inline with text. Thin, geometric, friendly line icons.
Also used for the phone mockup's status-bar glyphs (`SignalFull02Icon`, `WifiFullSignalIcon`,
`BatteryFullIcon` — see §13.1) rather than OS-specific glyph fonts, which don't render
cross-platform.

---

## 7. Logo / brand mark

**The actual artwork, not a redraw.** `closer/static/closer_logo.png` (the chat-bubble +
opposing-arrows mark, "the back-and-forth") is used as-is — a first pass hand-redrew it as an
SVG, but the redraw wasn't accurate to the original proportions, so that was scrapped per direct
feedback in favor of processing the real asset:

1. The source PNG has no alpha channel (flat white background) — background removed by treating
   luminance as inverse alpha (dark ink → opaque, white → transparent), auto-cropped to the ink's
   bounding box.
2. Recolored per context (same processed alpha mask, different fill):
   - `public/logo-mark.png` — `#2CDD85` (the dark-theme `--primary`) for the site header.
   - `public/logo-mark-print.png` — `#007339` (the light-mode fill color) for the light
     printable card (§1.4's exception).
3. `public/favicon.png` — the same mark composited onto a rounded dark tile (`#0E1016`, matching
   `--background`), 256×256, for the browser tab.

`src/components/Logo.tsx` renders `logo-mark.png` as a plain `<img>` (no SVG) next to a DM Sans
Bold "Closer" wordmark in `text-foreground`.

---

## 8. Components

Ported from BidPilot's shadcn "new-york" primitives (`class-variance-authority` + `cn()` =
`twMerge(clsx(...))`), simplified for a static site with no polymorphism needs (`asChild`/Radix
`Slot` dropped — nothing here needs to render as a different element):

- **Button** — variants `default | destructive | outline | secondary | ghost | link | pill`;
  sizes `default | sm | lg | xl | icon`. The `pill` variant (`rounded-full`, added beyond
  BidPilot's rounded-rect-only set) is the marketing CTA shape, with a nested circular icon chip
  on the trailing edge for the hero's primary CTA.
- **Badge** — `rounded-full`, `text-xs font-medium`, variants `default | secondary | outline |
  accent`. Vehicle for the status-color mapping in §1.3.
- **Card** — `rounded-2xl border bg-card`, sub-parts `CardHeader / CardTitle / CardDescription /
  CardContent / CardFooter`.
- **Nav** — a detached floating pill (not edge-to-edge), material provided by the liquid-glass
  engine (§13.2) rather than a plain Tailwind `backdrop-blur`.

---

## 9. Motion

| Token | Value | Use |
|---|---|---|
| `--ease-out-soft` | `cubic-bezier(0.16, 1, 0.3, 1)` | scroll reveals |
| `--ease-spring` | `cubic-bezier(0.32, 0.72, 0, 1)` | snappier UI transitions, button presses |

Rules:
- **Never** `linear` or default `ease-in-out`.
- Scroll-entry: fade-up + blur (`translateY(28px) blur(6px) opacity:0` → `translateY(0) blur(0)
  opacity:1`), 700–900ms, via `IntersectionObserver` (`src/components/Reveal.tsx`, the `.reveal`
  / `.reveal.is-visible` pair in `src/index.css`) — never a scroll-position listener.
- Micro-interactions (button hover/press): 150–250ms.
- The pulsing "live" status dot (`animate-pulse-dot`, ring pulse keyed to `--primary`) marks
  anything the page claims is "live."
- Respects `prefers-reduced-motion` (the `.reveal` transition is disabled outright under it).
- Animate only `transform` and `opacity`. `backdrop-blur`/glass effects only on the fixed nav,
  never on scrolling content.

### 9.1 Dither hero background

`src/components/DitherDots.tsx` — the hero's background texture, replacing an earlier
gradient-glow blob (§5). Despite the filename (kept for import stability, not worth the churn of
renaming), it draws **squares, not circles** — `ctx.fillRect`, not `ctx.arc`, per the sharp/
geometric direction (§4). A `<canvas>`, not a static image: a fixed grid (24px spacing, 2.6px
square) drawn once per `ResizeObserver` fire, then redrawn every frame via
`requestAnimationFrame` with each square's alpha driven by `sin(t · speed · squareSpeed +
squarePhase)` — an independent phase and speed multiplier per square (both randomized once at
grid-build time, not per frame) so the field reads as organic flicker rather than a uniform
pulse. Color is plain white at low alpha (`0.05`–`0.34`) rather than a hardcoded hex, so it
stays "background, but a bit lighter" without needing to track `--background`'s exact value.
Faded out well before the fold — not gradually across the whole (very tall, phone-extending)
hero section — via a `mask-image: linear-gradient(to_bottom, black_0%, black_10%,
transparent_35%)` on the canvas element (the one sanctioned "gradient": an invisible alpha mask,
not a visible color gradient — see §5). Falls back to a single static draw (no rAF loop) under
`prefers-reduced-motion`.

Reused a second time in the final CTA panel (`CTA.tsx`), this time with a
`radial-gradient(ellipse_60%_100%_at_50%_50%, black_0%, transparent_75%)` mask instead of the
hero's top-to-bottom fade — a soft dither field centered on the panel rather than one that reads
top-down, since the CTA is a self-contained block, not a full-bleed hero.

---

## 10. Voice & content rules

Verified, verbatim phrases already established in the codebase — reuse rather than paraphrase:

- "An AI negotiation coach that lives in iMessage."
- "No LLM ever estimates the floor."
- "The game theory is real, deterministic, and inspectable."
- "The bluff called by math."

Hero copy went through a few live rounds before landing: "Know what to send. Call the bluff."
→ "Closer, the negotiation copilot." → its final form, **"Introducing Closer. Your negotiation
copilot."** (H1) / **"Text Closer a car listing. It researches the real value, then coaches
every counter. No LLM ever estimates the floor."** (subhead, unchanged throughout) — a
product-launch framing, reusing the verbatim "No LLM ever estimates the floor" line rather than
paraphrasing it. The hero also dropped its eyebrow badge (`AI negotiation coach · lives in
iMessage`) entirely — the H1 carries that on its own now.

Ground rules for anyone writing more page copy:
- **Never mention Terac**, in any form, anywhere on the page.
- Don't oversell what's mocked. Research is genuinely live in `RESEARCH_MODE=live`; the demo arc
  is a real scripted scenario pulled from the actual test fixture, not a fabricated number —
  currently the **2008 Toyota Camry LE** arc (§14), not the earlier placeholder Mazda CX-5 one.
- The backend runs locally (long-running uvicorn), not on Vercel.
- **There is no dashboard, ever.** Confirmed explicitly in the post-Sync-1 `CLAUDE.md`: "The
  product surface is iMessage. There is no dashboard." The *only* sanctioned web surface is
  "a one-page landing carrying the Linq share-link QR code — never a dashboard." That's this
  page. Don't imply a dashboard exists or is coming.
- Don't invent a resolution. The canonical fixture (§14) doesn't close — it ends mid-negotiation
  (`state: NEGOTIATING`, `closed_price: null`). Say so plainly rather than writing a fake ending.

---

## 11. Implementation status

**Built and running.** `web/` — Vite + React + TypeScript, Tailwind v4 via `@tailwindcss/vite`
(matching `ideas-dash`'s toolchain, not Next.js). `npm run dev` serves it; `npx tsc -b`
type-checks clean; manually QA'd in Chrome at desktop and tablet widths with no console errors.

- `src/index.css` — the dark token set (§1–§5) + motion utilities (§9).
- `src/components/ui/{button,card,badge}.tsx` + `src/lib/utils.ts` — ported primitives (§8).
- `src/components/Logo.tsx` + `public/{logo-mark,logo-mark-print,favicon}.png` — real-asset logo
  (§7).
- `src/components/Reveal.tsx` — scroll-reveal wrapper (§9).
- `src/components/Phone.tsx` + `public/phone-mockup.png` — the hero's phone bezel with a dark
  iMessage-style placeholder thread inside it (§13.1).
- `src/lib/liquidGlass.ts` + `src/components/sections/Nav.tsx` — the real SVG-refraction glass
  nav (§13.2).
- Full page: `Nav`, `Hero`, `HowItWorks`, `Engine`, `Proof` (the Mazda CX-5 arc as an annotated
  timeline), `Trust`, `CTA`, `TryItLive` (QR contact cards), `Footer` — assembled in
  `src/App.tsx`.
- QR contact cards (buyer: Closer AI `+12052611117`, seller: Hackathon Seller `+12054909563`),
  static SVGs at `public/qr-{buyer,seller}.svg`, sms: deep links with grounded pre-filled openers
  in `src/lib/contacts.ts`, plus the standalone light-themed printable card at
  `public/print-cards.html` (§1.4).

Known gap, called out rather than silently shipped: the floating nav hides its links below the
`md` breakpoint with no hamburger fallback — mobile visitors reach every section by scrolling
(the footer repeats the same links). Deliberate scope cut, not an oversight.

---

## 12. Decisions log

| # | Decision | Resolution |
|---|---|---|
| 1 | Brand color | Own hue, six live rounds, landed at **`88°`, `100%/50%`** (`#88FF00`) — a deliberate "mix of now and before" between a too-yellow `#B8FF00` (`76.7°`) and a too-pure-green `#55FF00` (`100°`). Full history in §1.1.1. |
| 2 | Logo / brand mark | **The real PNG asset**, not a hand-redrawn SVG — the first SVG redraw wasn't accurate, scrapped per direct feedback. See §7. |
| 3 | The *other* dark panel (`negotiation-dashboard-mockup.html`) | Left alone. Not in scope; not touched. See §1.4. |
| 4 | Icon system | Hugeicons, matching BidPilot exactly. |
| 5 | Framework | Vite + React + TypeScript, not Next.js — matching `ideas-dash`'s toolchain. |
| 6 | **Site theme** | **Dark**, not light — converted mid-build per direct request. Later corrected again to **neutral grayscale** (`0 0%` background/card/border family) after an interim navy-tinted (`224°`) version read as "bluish." See §1. |
| 7 | Hero visual | A phone mockup (real bezel asset from the Temperance project) with a dark iMessage-placeholder thread inside it, replacing an earlier belief-curve stat card. No glow behind it — removed per feedback along with every other decorative gradient/glow (§5). See §13.1. |
| 8 | Nav material | Tried the real SVG-refraction "liquid glass" engine (ported from the Temperance project) with several rounds of tuning (`frostBlur` up, `edgeHighlight` to `0`, squared off per §4) — then **removed entirely** per direct feedback and replaced with a flat `bg-secondary` surface, no blur, no border. `src/lib/liquidGlass.ts` deleted as dead code. See §13.2. |
| 9 | Hero layout | Single centered column (headline → subhead → CTA → phone, stacked), not the original two-column side-by-side split — the phone is allowed to run below the fold. |
| 10 | Hero background | No gradients/glow blobs anywhere — an animated square-dither canvas instead (`DitherDots`, §9.1: squares not circles, size *and* alpha both animate, faded out well before the fold via an alpha mask). |
| 11 | Hero eyebrow badge | Removed (`AI negotiation coach · lives in iMessage`) — the H1 now carries that on its own. |
| 12 | Hero copy, final form | "Introducing Closer. Your negotiation copilot." — see §10 for the full iteration history. |
| 13 | **All edges, sharp and geometric** | The entire radius scale zeroed (§4); every hardcoded `rounded-full`/`rounded-[...]` swept out by hand across every component, including small circular elements (status dots, timeline markers, the phone's avatar chip) — those are squares now too. One exception: the phone bezel's screen-corner mask, which matches the real device photo. |
| 14 | Hero H1 weight | `font-medium` (500), not `font-bold` (700) — lighter per direct feedback, scoped to the hero H1 only, not a global type-weight sweep. |
| 15 | Hero heading hierarchy | Tried three shapes in sequence: (a) one `h1`, two lines, both full display size; (b) one `h1` line + a smaller separate tagline tier below it; (c) both merged into a single `h1` line, `whitespace-nowrap` + fluid `clamp()` sizing, forced to fit one line at any viewport. **Landed back on (a)** — one `h1`, two lines ("Introducing Closer." / "Your negotiation copilot."), same size/weight throughout — but at a reduced scale (`44px → 64px`, down from the original `52px → 76px`) per direct feedback ("make the overall title text smaller a bit"). |
| 16 | Dither animation | Squares now animate both alpha *and* scale (`0.5×`–`1.6×`) per the same per-square phase/speed, not alpha alone — "slightly grow and shrink." |
| 17 | Nav structure | No longer one continuous bar. Three separate blocks — logo, nav-links (sized to content, ends right after "Try it"), CTA — each on a shared `h-11` height (unified per feedback; they'd drifted to three different heights: a `py`-driven logo block, a `py`-driven links block, and the button's own fixed `h-8`), with `gap-1` between them instead of living inside one bar. |
| 18 | Content sync (Sync 1) | Pulled the latest GitHub updates and rewrote every section that referenced the placeholder Mazda CX-5 demo to use the real, verified `deal_camry.json` fixture (2008 Camry LE, Marcus the seller agent) instead — including removing a fabricated "closed deal" claim from the Hero stat badge and HowItWorks' close step, since the canonical fixture ends `NEGOTIATING`, not closed. See §10. |
| 19 | Section hover graphics | Added custom interactive hover graphics to all four bento cards in HowItWorks, then to Engine and Trust too — then **reverted Engine and Trust** back to the plain icon-chip layout per direct feedback. Graphics now live only in HowItWorks (§8). |
| 20 | Engine section background | Dropped the `bg-paper` panel color that set Engine apart from the rest of the page — it now sits on the same background as every other section, no banding. |
| 21 | CTA panel | Swapped the flat brand-green fill for the same `bg-secondary` panel color as the nav, with `DitherDots` layered on top (radial mask, §9.1) for texture. The CTA button is now the green element (`default` button variant) instead of an inverted white pill on a green field. |
| 22 | Try-it-live contact cards | Redesigned `ContactCard` to lead with name + one-line bio, then a large QR code, then the phone number as a "tap or scan to text" line. Dropped the verbatim SMS-opener quote from the card body — it's still the real text sent (`lib/contacts.ts`), just no longer echoed on-page. |
| 23 | Proof section heading + speaker tags | Heading changed from "One real negotiation, mid-fight" to "One real negotiation, turn by turn" — the fight framing read wrong. Each timeline entry initially carried a `MARCUS` / `CLOSER` eyebrow tag; superseded by #25 below once the buyer/advisor framing was corrected. |
| 24 | **Product-accuracy audit — Closer is an advisor, not the buyer** | Ran a full research-and-audit pass (backend source, README, DEMO.md, LINQ.md, `CLOSER_BUILD_PROMPT.md`, the `deal_camry.json` fixture and its test harness) to ground-truth exactly who talks to whom. Confirmed: the site visitor is always the buyer; Closer only ever exchanges messages with that human over one number; it never texts a seller directly. Every "seller" line in the fixture is the buyer's own third-person relay ("He says …") typed or screenshotted into the Closer thread — not Marcus's raw text arriving at Closer. Marcus (`+12054909563`) is a fully separate product/thread the visitor can text themselves. This corrected a real misrepresentation on the previous build of the page, where copy and the Proof timeline read as if Closer negotiated directly with Marcus. |
| 25 | Proof section — corrected speaker labels | Per #24: the `MARCUS` eyebrow tag was replaced with **`YOU RELAYED`** (the quote text was already third-person buyer paraphrase — the label was the part that was wrong) and `CLOSER` became **`CLOSER RECOMMENDS`**. Intro and closing copy reworded to state the relay explicitly ("the buyer's relay of what Marcus said, then Closer's actual engine response back"; "Closer keeps telling the buyer to hold at $4,992"). Kept the existing single-timeline visual rather than rebuilding into two separate thread columns — a deliberate minimal-change call, not a missed opportunity. |
| 26 | Other buyer/advisor corrections from #24 | `Phone.tsx`'s hero mini-chat had its bubble direction inverted — the buyer's own relayed text was rendering as the *incoming* (left/gray) bubble and Closer's coaching as the *outgoing* (right/colored) one, backwards from real iMessage. Fixed (`from: "me" | "closer"`, `mine = from === "me"`). `TryItLive.tsx`'s subtitle "two sides of the same thread" implied one shared conversation; changed to "two sides of one negotiation" — scanning either QR opens a genuinely separate SMS thread. `HowItWorks.tsx`'s section heading "One thread. Four moves. **A closed deal.**" asserted an outcome the canonical fixture never reaches (`state: NEGOTIATING`); changed to "Under fair value." to match capability without a fabricated close (same category of fix as #18, just missed the first time). |
| 27 | CTA dither — real stacking-context bug, not a tuning issue | The CTA panel's `DitherDots` was invisible on first ship. Root cause: `Reveal`'s `.is-visible` class sets `transform: translateY(0)` and `filter: blur(0)` (plus `will-change`) — none of these are the literal keyword `none`, so per spec `Reveal`'s wrapper establishes its own stacking context. The canvas's `-z-10` escaped past its immediate `relative` parent (which has no stacking context of its own — `position: relative` alone doesn't create one) up to that `Reveal` wrapper, painting behind the panel's own opaque `bg-secondary` fill instead of on top of it. Confirmed by sampling the canvas's own pixel buffer (real alpha data, correctly drawing) against the fact that nothing was visible on screen. Fixed by adding `isolate` to the panel div, forcing a local stacking context so the negative z-index can't escape. Mask retuned afterward to a subtle center-weighted fade (`ellipse_55%_80%_at_50%_50%, black_0%, transparent_65%`) now that it's actually rendering. |

Nothing outstanding.

---

## 13. Assets ported from the Temperance project

Two pieces of Arshawn's own prior work
(`/Users/arshawnarbabi/Downloads/Temperance/Temperance_Website`) were pulled into this project
directly, per request mid-build.

### 13.1 Phone mockup hero visual

`public/phone-mockup.png` — copied verbatim from `Temperance_Website/public/phone_mockup.png`.
A transparent-cutout PNG bezel (1400×2868, only the frame/notch/buttons are opaque; the screen
area is a true alpha cutout, not a flat white rectangle), reused across several Temperance
components. Positioning technique (`src/components/Phone.tsx`), also ported verbatim:

```css
/* screen-content layer sits BEHIND the frame image, positioned as % of the frame box */
top: 1.53%; left: 4.29%; right: 4.21%; bottom: 1.5%; border-radius: 9% / 4.4%;
```
The frame `<img>` sits on top with `object-fit: contain`; the screen div behind it is clipped
with `overflow: hidden` to that same rounded rect.

Screen content is original to Closer, not reused from Temperance: a dark iMessage-style thread
(status bar with Hugeicons signal/wifi/battery glyphs, a "Closer AI" contact header using the
processed logo mark, then the verified Mazda CX-5 demo script rendered as real chat bubbles —
outgoing "Closer" bubbles filled `#00734D` with white text, incoming "seller" bubbles a neutral
dark gray `#24262d`). Sized with CSS container queries (`@container` + `cqw` units) so the whole
screen scales proportionally at any rendered phone width, rather than fixed pixel sizes.

### 13.2 Liquid-glass nav — tried, then removed

**Current state: not used.** `src/lib/liquidGlass.ts` was copied verbatim from
`Temperance_Website/lib/liquidGlass.ts` (itself a port of `rizroze/liquid-glass`, MIT) and
mounted on the nav — the *real* SVG-refraction effect, not a CSS approximation: a displacement
map drawn on an off-screen `<canvas>`, serialized to a data URI, fed into a hand-built SVG
`<filter>` (three `feDisplacementMap` passes per RGB channel → chromatic aberration, recombined
with `feColorMatrix` + `feBlend mode="screen"`), referenced via `backdrop-filter: url(#id)
blur(...) saturate(...)`. Chromium-only, with an automatic plain-`blur()` fallback elsewhere.

It was replaced per direct feedback ("instead of the nav bar being blur glass, make it just a
bit lighter per the neutral color steps") with a flat, non-blurred surface — `bg-secondary`
(§1.1, one step up from `--background` on the neutral grayscale ladder), no `backdrop-filter`,
no border, sharp corners (§4). `src/lib/liquidGlass.ts` was deleted as dead code once nothing
referenced it. This paragraph is kept as a record of what was tried and why it didn't stay, in
case a future session wants the effect back — the file is still intact at its source in
`Temperance_Website/lib/liquidGlass.ts` if so.
`edgeHighlight` produces the specular top/bottom rim highlight as an `inset box-shadow` pair;
`shadowOpacity` is nudged via the instance's own `.update()` API when the page scrolls past 8px,
rather than a separate Tailwind shadow class (inline styles set by the engine would just
override a class anyway).
