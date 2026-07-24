import type { ColorSlot } from "../data";

/** CSS var reference for a track's fixed categorical slot. Never cycled, never reassigned. */
export function slotVar(slot: ColorSlot): string {
  return `var(--slot-${slot})`;
}
