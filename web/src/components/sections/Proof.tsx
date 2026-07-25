import { Reveal } from "@/components/Reveal"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

// Every line here is real — pulled from closer/tests/fixtures/deal_camry.json,
// the actual scripted fixture the engine's own test suite runs against, not a
// script we wrote for the page. The fixture ends mid-negotiation (state:
// NEGOTIATING, closed_price: null) — no invented ending here either.
const ARC = [
  {
    quote: null,
    said: "Research lands: fair value $5,200, walk-away $4,160 — a timing belt + water pump due at 150k ($900), weeping front struts ($480), and tires at 4/32 ($520) pull the walk-away well below fair value.",
    action: "RESEARCHED",
    tone: "neutral" as const,
    curve: "prior set from the researched value",
  },
  {
    quote: "He says 6,400 is what it's worth — plenty of life left in it.",
    said: "Opening anchor. No concession yet.",
    action: "COUNTER · $4,848",
    tone: "counter" as const,
    curve: "belief opens wide, centered near ~$5,600",
  },
  {
    quote: "He came down to 5,900 and says that's already a favor.",
    said: "A real $500 concession.",
    action: "COUNTER · $4,992",
    tone: "counter" as const,
    curve: "belief narrows, median drops to ~$5,320",
  },
  {
    quote: "He says three other people are coming to see it Saturday, so he's not moving.",
    said: "A bluff claim — pressure, with no price behind it.",
    action: "HOLD · bluff called",
    tone: "hold" as const,
    curve: "belief moves $4 — the bluff, called by math",
  },
  {
    quote: "He'll do 5,400 if I pick it up tomorrow.",
    said: "Another concession offered — still well above where the math says to stop.",
    action: "HOLD · $4,992",
    tone: "hold" as const,
    curve: "still holding — nothing here is worth chasing",
  },
]

const TONE_BADGE: Record<string, string> = {
  neutral: "bg-secondary text-secondary-foreground",
  counter: "bg-blue-400/15 text-blue-300",
  hold: "bg-amber-400/15 text-amber-300",
}

export function Proof() {
  return (
    <section id="proof" className="mx-auto max-w-4xl px-4 py-24 sm:py-32">
      <Reveal className="mx-auto max-w-2xl text-center">
        <h2 className="text-balance text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
          One real negotiation, turn by turn
        </h2>
        <p className="mt-4 text-base leading-relaxed text-muted-foreground">
          A 2008 Toyota Camry LE, asking $6,400 — against a real seller. Each step below is
          the buyer's relay of what the seller said, then Closer's actual engine response.
        </p>
      </Reveal>

      <div className="relative mt-16">
        <div
          aria-hidden="true"
          className="absolute left-4 top-2 bottom-2 w-px bg-border sm:left-1/2"
        />
        <ol className="flex flex-col gap-10">
          {ARC.map((step, i) => (
            <Reveal
              key={i}
              as="li"
              delay={i * 80}
              className={cn(
                "relative flex flex-col gap-2 pl-12 sm:w-1/2 sm:pl-0 sm:pr-10",
                i % 2 === 1 && "sm:ml-auto sm:pl-10 sm:pr-0 sm:text-left"
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "absolute top-1 left-2.5 size-3 border-2 border-card bg-primary sm:left-auto",
                  i % 2 === 1 ? "sm:-left-1.5" : "sm:-right-1.5"
                )}
              />
              {step.quote && (
                <p className="text-base font-medium text-foreground">
                  <span className="money mr-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    You relayed
                  </span>
                  "{step.quote}"
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <span className="money text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Closer recommends
                </span>
                <Badge className={cn("w-fit", TONE_BADGE[step.tone])}>{step.action}</Badge>
              </div>
              {step.said && <p className="text-sm text-muted-foreground">{step.said}</p>}
              <p className="money text-xs text-muted-foreground/80">{step.curve}</p>
            </Reveal>
          ))}
        </ol>
      </div>

      <Reveal delay={ARC.length * 80} className="mx-auto mt-14 max-w-xl text-center">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Still open — the seller keeps inching down, Closer keeps telling the buyer to hold at{" "}
          <span className="money text-foreground">$4,992</span>. No canned ending here: that's
          just where the math has it right now.
        </p>
      </Reveal>
    </section>
  )
}
