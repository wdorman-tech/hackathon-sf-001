import { cn } from "@/lib/utils"

/** The actual mark from closer/static/closer_logo.png — bg removed, recolored to brand green. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/logo-mark.png"
      alt=""
      className={cn("h-7 w-auto object-contain", className)}
    />
  )
}

export function Logo({
  className,
  markClassName,
  wordmark = true,
}: {
  className?: string
  markClassName?: string
  wordmark?: boolean
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark className={cn("h-7", markClassName)} />
      {wordmark && (
        <span className="text-[19px] font-bold tracking-[-0.02em] text-foreground">
          Closer
        </span>
      )}
    </span>
  )
}
