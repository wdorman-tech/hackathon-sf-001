import { cn } from "@/lib/utils"

/**
 * Dot-matrix + sparse hairline texture inside a margin strip — the gap
 * between the viewport edge and the vertical edge-line (EdgeLines.tsx).
 * Mount inside a `position: relative` section that spans the full viewport
 * width (not one already clipped to a max-w content column).
 */
export function MarginDecor({ side }: { side: "l" | "r" }) {
  return <div className={cn("edge-decor", side === "l" ? "edge-decor-l" : "edge-decor-r")} aria-hidden="true" />
}
