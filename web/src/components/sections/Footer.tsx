import { Logo } from "@/components/Logo"

const LINKS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#engine", label: "The engine" },
  { href: "#proof", label: "Watch it work" },
]

export function Footer() {
  return (
    <footer className="mx-auto max-w-6xl px-4 py-14">
      <div className="flex flex-col items-center gap-6 border-t border-border pt-10 text-center sm:flex-row sm:justify-between sm:text-left">
        <div>
          <Logo />
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            An AI negotiation coach that lives in iMessage.
          </p>
        </div>
        <ul className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
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
      </div>
      <p className="mt-8 text-center text-xs text-muted-foreground/70 sm:text-left">
        © {new Date().getFullYear()} Closer. Built for a hackathon demo.
      </p>
    </footer>
  )
}
