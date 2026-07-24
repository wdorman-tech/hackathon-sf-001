import { Reveal } from "@/components/Reveal"
import { Phone } from "@/components/Phone"
import { DitherDots } from "@/components/DitherDots"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden px-4 pt-28 pb-20 sm:pt-32">
      <DitherDots className="-z-10 [mask-image:linear-gradient(to_bottom,black_0%,black_10%,transparent_35%)]" />

      <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        <Reveal>
          <h1 className="text-balance text-[44px] font-medium leading-[1.04] tracking-[-0.03em] text-foreground sm:text-6xl lg:text-[64px]">
            Introducing Closer.
            <br />
            Your negotiation copilot.
          </h1>
        </Reveal>

        <Reveal delay={80}>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
            Text Closer a car listing. It researches the real value, then coaches every
            counter.{" "}
            <span className="font-medium text-foreground">
              No LLM ever estimates the floor.
            </span>
          </p>
        </Reveal>

        <Reveal delay={240}>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <a
              href="#try"
              className={cn(
                buttonVariants({ variant: "pill", size: "xl" }),
                "group/cta gap-0 pr-2"
              )}
            >
              <span className="pl-1">Text Closer, try it now</span>
              <span className="ml-3 flex size-9 items-center justify-center bg-white/15 transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover/cta:translate-x-0.5 group-hover/cta:-translate-y-px">
                →
              </span>
            </a>
            <a
              href="#engine"
              className={buttonVariants({ variant: "ghost", size: "xl" })}
            >
              See how the math works
            </a>
          </div>
        </Reveal>
      </div>

      <Reveal delay={200} className="relative mx-auto mt-10 w-fit sm:mt-12">
        <div className="relative w-[260px] sm:w-[320px] lg:w-[360px]">
          <Phone />
        </div>
      </Reveal>
    </section>
  )
}
