import { useEffect, useState } from "react"
import { Logo } from "@/components/Logo"
import { buttonVariants } from "@/components/ui/button"
import { BUYER_SMS_HREF } from "@/lib/contacts"
import { cn } from "@/lib/utils"

const LINKS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#engine", label: "The engine" },
  { href: "#proof", label: "Watch it work" },
]

const BLOCK_HEIGHT = "h-11"

export function Nav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const shadow = scrolled
    ? "shadow-[0_20px_50px_-20px_rgba(0,0,0,0.5)]"
    : "shadow-[0_10px_30px_-18px_rgba(0,0,0,0.35)]"

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-30 px-4 pt-4 sm:pt-6">
      {/* full-width row, aligned with the same max-w-6xl margin the page sections use */}
      <div className="pointer-events-auto mx-auto flex w-full max-w-6xl items-center gap-3">
        {/* logo + links — one connected bar that grows to fill the row */}
        <div
          className={cn(
            BLOCK_HEIGHT,
            "flex flex-1 items-center gap-8 bg-secondary px-4 transition-shadow duration-300",
            shadow
          )}
        >
          <a href="#top" className="flex shrink-0 items-center">
            <Logo />
          </a>
          <nav className="ml-auto hidden items-center md:flex">
            <ul className="flex items-center gap-6">
              {LINKS.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {/* CTA — its own block */}
        <a
          href={BUYER_SMS_HREF}
          className={cn(
            buttonVariants({ variant: "pill", size: "sm" }),
            BLOCK_HEIGHT,
            "shrink-0 px-4"
          )}
        >
          Text Closer
        </a>
      </div>
    </header>
  )
}
