import { useRef, useState, type FocusEvent, type PointerEvent } from "react";

export interface TooltipState<T> {
  data: T;
  x: number;
  y: number;
}

/**
 * Shared hover/focus tooltip positioning. Tooltips enhance, never gate —
 * every chart using this also ships direct labels and/or a table view.
 */
export function useTooltip<T>() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState<T> | null>(null);

  function show(e: PointerEvent<Element> | FocusEvent<Element>, data: T) {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const target = e.currentTarget as Element;
    const targetRect = target.getBoundingClientRect();
    const clientX = targetRect.left + targetRect.width / 2;
    const clientY = targetRect.top;
    setTooltip({ data, x: clientX - rect.left, y: clientY - rect.top });
  }

  function hide() {
    setTooltip(null);
  }

  return { containerRef, tooltip, show, hide };
}
