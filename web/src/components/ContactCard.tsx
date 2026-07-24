import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"

export function ContactCard({
  role,
  name,
  phoneDisplay,
  smsHref,
  qrSrc,
  blurb,
  className,
}: {
  role: string
  name: string
  phoneDisplay: string
  smsHref: string
  qrSrc: string
  blurb: string
  className?: string
}) {
  return (
    <div className={cn("bg-white/[0.03] p-2 ring-1 ring-white/10", className)}>
      <div className="flex h-full flex-col items-center gap-5 bg-card p-7 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
        <Badge variant="accent">{role}</Badge>
        <div>
          <p className="text-lg font-semibold text-foreground">{name}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{blurb}</p>
        </div>

        <a
          href={smsHref}
          className="group/qr mt-1 block shrink-0 border border-border bg-white p-4 transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] hover:scale-[1.03]"
          aria-label={`Text ${name}`}
        >
          <img src={qrSrc} alt={`QR code to text ${name}`} className="size-48 sm:size-52" />
        </a>

        <a
          href={smsHref}
          className="money mt-1 text-sm font-medium text-primary hover:underline"
        >
          {phoneDisplay} — tap or scan to text →
        </a>
      </div>
    </div>
  )
}
