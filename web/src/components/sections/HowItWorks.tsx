import { HugeiconsIcon } from "@hugeicons/react"
import {
  LinkSquare01Icon,
  ArrowRight01Icon,
  Search01Icon,
  HandshakeIcon,
} from "@hugeicons/core-free-icons"
import { Reveal } from "@/components/Reveal"
import { cn } from "@/lib/utils"

/* ── Step 1 — "Text the listing": a link chip that visibly sends on hover ── */
function SendGraphic() {
  return (
    <div className="flex h-full min-h-56 items-center justify-center bg-background/40 px-6">
      <div className="flex w-full max-w-sm items-center gap-3 border border-border bg-card px-5 py-4 transition-colors duration-300 group-hover:border-primary/60">
        <HugeiconsIcon
          icon={LinkSquare01Icon}
          strokeWidth={1.5}
          className="size-6 shrink-0 text-muted-foreground"
        />
        <span className="money truncate text-sm text-muted-foreground">
          listing.link/2008-camry-le
        </span>
        <HugeiconsIcon
          icon={ArrowRight01Icon}
          strokeWidth={2}
          className="ml-auto size-6 shrink-0 text-primary transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-2"
        />
      </div>
    </div>
  )
}

/* ── Step 2 — "Researches, with receipts": result rows that scan + light up ── */
function ResearchGraphic() {
  const rows = [78, 92, 60, 82]
  return (
    <div className="relative flex h-full min-h-56 flex-col justify-center gap-4 overflow-hidden bg-background/40 px-8">
      {rows.map((w, i) => (
        <div key={i} className="flex items-center gap-3">
          <span className="size-3 shrink-0 bg-accent-foreground/40 transition-colors duration-300 group-hover:bg-primary" />
          <span
            className="h-2.5 bg-border transition-colors duration-500 group-hover:bg-muted-foreground/60"
            style={{ width: `${w}%` }}
          />
        </div>
      ))}
      <HugeiconsIcon
        icon={Search01Icon}
        strokeWidth={1.5}
        className="absolute top-1/2 left-[-20%] size-14 -translate-y-1/2 text-primary opacity-0 transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:left-[105%] group-hover:opacity-90"
      />
    </div>
  )
}

/* ── Step 3 — "Coach every counter": the belief curve collapsing to a spike ── */
const BARS = [
  { base: "h-3", hover: "group-hover:h-1.5", delay: "delay-300" },
  { base: "h-8", hover: "group-hover:h-3", delay: "delay-150" },
  { base: "h-14", hover: "group-hover:h-5", delay: "delay-75" },
  { base: "h-20", hover: "group-hover:h-28", delay: "delay-0", spike: true },
  { base: "h-14", hover: "group-hover:h-5", delay: "delay-75" },
  { base: "h-8", hover: "group-hover:h-3", delay: "delay-150" },
  { base: "h-3", hover: "group-hover:h-1.5", delay: "delay-300" },
]
function BeliefGraphic() {
  return (
    <div className="flex h-full min-h-56 items-end justify-center gap-3 bg-background/40 px-6 pb-8">
      {BARS.map((bar, i) => (
        <span
          key={i}
          className={cn(
            "w-4 bg-muted-foreground/40 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
            bar.base,
            bar.hover,
            bar.delay,
            bar.spike && "group-hover:bg-primary"
          )}
        />
      ))}
    </div>
  )
}

/* ── Step 4 — "Close below fair value": asking price crossed out, the actual counter pops ── */
function CloseGraphic() {
  return (
    <div className="flex h-full min-h-56 flex-col items-center justify-center gap-3 bg-background/40">
      <span className="money text-xl text-muted-foreground line-through decoration-destructive/70 decoration-2 transition-opacity duration-300 group-hover:opacity-50">
        $6,400 asking
      </span>
      <span className="money flex items-center gap-3 text-5xl font-semibold text-foreground transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:scale-110 group-hover:text-primary">
        <HugeiconsIcon icon={HandshakeIcon} strokeWidth={2} className="size-9" />
        $4,992
      </span>
    </div>
  )
}

const STEPS = [
  {
    title: "Text the listing",
    body: "Send Closer a link to a used-car listing over iMessage. It starts researching the second it lands.",
    Graphic: SendGraphic,
    span: "sm:col-span-7",
  },
  {
    title: "It researches, with receipts",
    body: "A bounded agentic loop reads the listing, searches for private-party comps, and returns a cited fair value, hidden costs, and red flags — sources included.",
    Graphic: ResearchGraphic,
    span: "sm:col-span-5",
  },
  {
    title: "Coach every counter",
    body: "Relay each seller reply — text or screenshot. Closer classifies it, updates its belief about their floor, and texts back the exact move.",
    Graphic: BeliefGraphic,
    span: "sm:col-span-5",
  },
  {
    title: "Close below fair value",
    body: "Every recommendation maximizes expected value against your walk-away price. You always know when to hold, counter, or walk.",
    Graphic: CloseGraphic,
    span: "sm:col-span-7",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl px-4 py-24 sm:py-32">
      <Reveal className="mx-auto max-w-2xl text-center">
        <h2 className="text-balance text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
          One thread. Four moves. Under fair value.
        </h2>
      </Reveal>

      <div className="relative mt-16 grid grid-cols-1 gap-6 sm:grid-cols-12">
        {STEPS.map((step, i) => (
          <Reveal key={step.title} delay={i * 90} className={step.span}>
            <div className="group flex h-full flex-col border border-border bg-card transition-colors duration-300 hover:border-primary/40">
              <step.Graphic />
              <div className="flex flex-1 flex-col gap-3 border-t border-border p-6">
                <p className="money text-xs text-muted-foreground">0{i + 1}</p>
                <h3 className="text-base font-semibold text-foreground">{step.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
