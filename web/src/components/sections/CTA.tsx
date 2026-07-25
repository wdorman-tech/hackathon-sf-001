import { Reveal } from "@/components/Reveal"
import { buttonVariants } from "@/components/ui/button"
import { DitherDots } from "@/components/DitherDots"
import { BUYER_SMS_HREF } from "@/lib/contacts"
import { cn } from "@/lib/utils"

export function CTA() {
  return (
    <section className="px-4 py-6">
      <Reveal className="mx-auto max-w-6xl">
        <div className="relative isolate overflow-hidden bg-secondary px-8 py-16 text-center sm:px-16 sm:py-20">
          <DitherDots className="-z-10 [mask-image:radial-gradient(ellipse_55%_80%_at_50%_50%,black_0%,transparent_65%)]" />
          <h2 className="text-balance relative mx-auto max-w-2xl text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
            Ready to see the math call a bluff?
          </h2>
          <p className="relative mx-auto mt-4 max-w-lg text-base text-muted-foreground">
            No install. No account. Just text it a listing.
          </p>
          <a
            href={BUYER_SMS_HREF}
            className={cn(buttonVariants({ size: "xl" }), "relative mt-9")}
          >
            Text Closer now
          </a>
        </div>
      </Reveal>
    </section>
  )
}
