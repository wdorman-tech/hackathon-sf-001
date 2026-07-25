import { HugeiconsIcon } from "@hugeicons/react"
import { Robot01Icon, Shield01Icon, WifiOff01Icon, Route01Icon } from "@hugeicons/core-free-icons"
import { Reveal } from "@/components/Reveal"

const PILLARS = [
  {
    icon: Robot01Icon,
    title: "One model, one provider",
    body: "Every LLM call — research, classify, draft, and screenshot vision — goes through a single Runware model id. No direct provider SDKs.",
  },
  {
    icon: Shield01Icon,
    title: "SSRF-guarded research",
    body: "Every fetch the research agent makes is validated against loopback, private, link-local, and metadata addresses — and every redirect hop is re-checked, not just the first.",
  },
  {
    icon: WifiOff01Icon,
    title: "Runs with zero keys",
    body: "The whole app still runs end-to-end without them — a deterministic rules-based classifier and a heuristic valuation take over. A dead network never kills the demo.",
  },
  {
    icon: Route01Icon,
    title: "Deterministic math",
    body: "The belief engine is pure numpy — it never imports a network client. Every recommendation is inspectable and reproducible.",
  },
]

export function Trust() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-24 sm:py-32">
      <Reveal className="mx-auto max-w-2xl text-center">
        <h2 className="text-balance text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
          The parts you can't see matter more
        </h2>
      </Reveal>

      <div className="mt-16 grid gap-5 sm:grid-cols-2">
        {PILLARS.map((pillar, i) => (
          <Reveal key={pillar.title} delay={i * 90}>
            <div className="flex h-full gap-4 border border-border bg-card p-6">
              <div className="flex size-11 shrink-0 items-center justify-center bg-accent text-accent-foreground">
                <HugeiconsIcon icon={pillar.icon} strokeWidth={1.5} className="size-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">{pillar.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {pillar.body}
                </p>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
