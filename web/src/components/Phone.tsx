import { HugeiconsIcon } from "@hugeicons/react"
import { SignalFull02Icon, WifiFullSignalIcon, BatteryFullIcon } from "@hugeicons/core-free-icons"
import { cn } from "@/lib/utils"
import { LogoMark } from "@/components/Logo"

/**
 * Phone bezel: public/phone-mockup.png (from the Temperance project), a
 * transparent-cutout PNG frame at a fixed 1400/2868 aspect ratio. The screen
 * content sits in a layer *behind* the frame image, positioned as percentages
 * of the frame box so it lines up with the PNG's cutout exactly.
 */
const SCREEN_INSET = {
  top: "1.53%",
  left: "4.29%",
  right: "4.21%",
  bottom: "1.5%",
  borderRadius: "9% / 4.4%",
}

function Bubble({
  from,
  children,
}: {
  from: "me" | "closer"
  children: React.ReactNode
}) {
  const mine = from === "me"
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[78%] px-[3.4cqw] py-[2.2cqw] text-[3.6cqw] leading-[1.32]",
          mine ? "bg-[#3B650B] text-white" : "bg-[#24262d] text-[#f2f3f5]"
        )}
      >
        {children}
      </div>
    </div>
  )
}

function PhoneScreenUI() {
  return (
    <div className="@container flex h-full w-full flex-col bg-[#08090c]">
      {/* status bar */}
      <div className="flex items-center justify-between px-[6cqw] pt-[3.2cqw] text-[3.1cqw] font-semibold text-white/90">
        <span>9:41</span>
        <span className="flex items-center gap-[1.6cqw] [&_svg]:size-[3.4cqw]">
          <HugeiconsIcon icon={SignalFull02Icon} strokeWidth={2} />
          <HugeiconsIcon icon={WifiFullSignalIcon} strokeWidth={2} />
          <HugeiconsIcon icon={BatteryFullIcon} strokeWidth={2} />
        </span>
      </div>

      {/* iMessage header */}
      <div className="flex flex-col items-center gap-[1.6cqw] border-b border-white/[0.08] px-[4cqw] pt-[2.4cqw] pb-[2.8cqw]">
        <div className="flex size-[11cqw] items-center justify-center bg-[#0f2c22]">
          <LogoMark className="h-[6cqw] w-auto" />
        </div>
        <p className="text-[3.4cqw] font-semibold text-white">Closer AI</p>
      </div>

      {/* message thread */}
      <div className="flex flex-1 flex-col justify-end gap-[2.6cqw] overflow-hidden px-[4cqw] pb-[3cqw]">
        <p className="mt-[2cqw] text-center text-[2.5cqw] uppercase tracking-[0.1em] text-white/35">
          Today 2:14 PM
        </p>
        <Bubble from="me">
          "He says three other people are coming to see it Saturday, so he's not moving."
        </Bubble>
        <Bubble from="closer">
          That's pressure, not a real move — the number barely budged. Hold at{" "}
          <span className="money font-semibold">$4,992</span>.
        </Bubble>
        <p className="money px-1 text-[2.6cqw] text-white/40">the curve moved $4 · bluff called</p>

        {/* input bar */}
        <div className="mt-[1.5cqw] flex items-center gap-[2cqw] border border-white/15 px-[3.4cqw] py-[2cqw] text-[3cqw] text-white/35">
          <span>iMessage</span>
        </div>
      </div>
    </div>
  )
}

export function Phone({ className }: { className?: string }) {
  return (
    <div
      className={cn("relative mx-auto w-full select-none", className)}
      style={{ aspectRatio: "1400 / 2868" }}
    >
      <div className="absolute overflow-hidden" style={SCREEN_INSET}>
        <PhoneScreenUI />
      </div>
      <img
        src="/phone-mockup.png"
        alt=""
        draggable={false}
        className="pointer-events-none absolute inset-0 h-full w-full object-contain"
      />
    </div>
  )
}
