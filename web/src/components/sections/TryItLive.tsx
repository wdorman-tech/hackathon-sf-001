import { Reveal } from "@/components/Reveal"
import { ContactCard } from "@/components/ContactCard"
import { BUYER_CONTACT, SELLER_CONTACT, BUYER_SMS_HREF, SELLER_SMS_HREF } from "@/lib/contacts"

export function TryItLive() {
  return (
    <section id="try" className="mx-auto max-w-5xl px-4 py-24 sm:py-32">
      <Reveal className="mx-auto max-w-2xl text-center">
        <h2 className="text-balance text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
          Scan. Text. Watch it negotiate.
        </h2>
        <p className="mt-4 text-base leading-relaxed text-muted-foreground">
          Two live numbers, two sides of one negotiation. Scan either card with your camera —
          it opens a pre-filled text, ready to send.
        </p>
      </Reveal>

      <div className="mt-14 grid gap-6 sm:grid-cols-2">
        <Reveal delay={80}>
          <ContactCard
            role={BUYER_CONTACT.role}
            name={BUYER_CONTACT.name}
            phoneDisplay={BUYER_CONTACT.phoneDisplay}
            smsHref={BUYER_SMS_HREF}
            qrSrc={BUYER_CONTACT.qrSrc}
            blurb={BUYER_CONTACT.blurb}
          />
        </Reveal>
        <Reveal delay={160}>
          <ContactCard
            role={SELLER_CONTACT.role}
            name={SELLER_CONTACT.name}
            phoneDisplay={SELLER_CONTACT.phoneDisplay}
            smsHref={SELLER_SMS_HREF}
            qrSrc={SELLER_CONTACT.qrSrc}
            blurb={SELLER_CONTACT.blurb}
          />
        </Reveal>
      </div>
    </section>
  )
}
