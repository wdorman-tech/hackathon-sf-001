import { HugeiconsIcon } from "@hugeicons/react"
import { File01Icon, Clock01Icon, AlertCircleIcon } from "@hugeicons/core-free-icons"
import { Reveal } from "@/components/Reveal"

const TERMS = [
  {
    icon: File01Icon,
    title: "Stated-price ceiling",
    body: "Their floor can't be above what they just offered. Every message narrows the range.",
  },
  {
    icon: Clock01Icon,
    title: "The gap model",
    body: "Firm, small concessions push the estimate up. Big, fast concessions shift it down and sharpen it. A real “final” offer collapses the curve to a spike.",
  },
  {
    icon: AlertCircleIcon,
    title: "Cheap talk",
    body: "“Someone's coming to look at it tomorrow” — a bluff claim with no price behind it, so the curve barely moves.",
  },
]

export function Engine() {
  return (
    <section id="engine" className="px-4 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-8">
          <Reveal className="lg:col-span-5">
            <h2 className="text-balance text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
              No LLM ever estimates the floor.
            </h2>
            <p className="mt-5 text-base leading-relaxed text-muted-foreground">
              The brain is a Bayesian belief engine — pure numpy, zero network calls. On every
              seller message it updates a probability distribution over their hidden floor
              price and recommends the expected-value-optimal counter. The LLM's only jobs:
              agentic research before the negotiation starts, and translating language into
              structure during it.
            </p>
            <div className="mt-8 border border-border bg-card p-5">
              <p className="money text-xs uppercase tracking-wide text-muted-foreground">
                The decision layer
              </p>
              <p className="mt-2 text-sm leading-relaxed text-foreground">
                Every counter maximizes{" "}
                <span className="money text-primary">
                  EV = (fair value − offer) × P(they'll accept)
                </span>
                . Hold through bluffs. Walk when the math says no deal exists above your
                walk-away. Never guess — compute.
              </p>
            </div>
          </Reveal>

          <div className="grid gap-5 lg:col-span-7 sm:grid-cols-3 lg:grid-cols-1">
            {TERMS.map((term, i) => (
              <Reveal key={term.title} delay={i * 100}>
                <div className="flex h-full gap-4 border border-border bg-card p-5 lg:items-start">
                  <div className="flex size-10 shrink-0 items-center justify-center bg-accent text-accent-foreground">
                    <HugeiconsIcon icon={term.icon} strokeWidth={1.5} className="size-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{term.title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                      {term.body}
                    </p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
