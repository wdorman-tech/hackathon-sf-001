import { useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

type RevealTag = "div" | "li" | "span" | "ul"

/**
 * Scroll-entry primitive (DESIGN.md §9): fade-up + blur via IntersectionObserver,
 * never a scroll-position listener. Pairs with the `.reveal` / `.reveal.is-visible`
 * CSS in index.css.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: ReactNode
  className?: string
  delay?: number
  as?: RevealTag
}) {
  const ref = useRef<HTMLElement | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.15 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const Tag = as as "div"

  return (
    <Tag
      ref={ref as React.Ref<HTMLDivElement>}
      className={cn("reveal", visible && "is-visible", className)}
      style={{ transitionDelay: visible ? `${delay}ms` : "0ms" }}
    >
      {children}
    </Tag>
  )
}
