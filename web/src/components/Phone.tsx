import { HugeiconsIcon } from "@hugeicons/react"
import {
  SignalFull02Icon,
  WifiFullSignalIcon,
  BatteryFullIcon,
  ArrowLeft01Icon,
  CameraVideoIcon,
  Add01Icon,
  Mic01Icon,
} from "@hugeicons/core-free-icons"
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

/**
 * The screen content is a deliberate exception to the sharp/geometric radius
 * rule (DESIGN.md §4) — the whole point is to read as a real iMessage
 * screenshot, and real iMessage is pill-shaped bubbles and a circular avatar.
 */
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
          "max-w-[78%] rounded-[4.6cqw] px-[3.6cqw] py-[2.3cqw] text-[3.6cqw] leading-[1.32] text-white",
          mine ? "bg-[#0A84FF]" : "bg-[#262628]"
        )}
      >
        {children}
      </div>
    </div>
  )
}

function PhoneScreenUI() {
  return (
    <div className="@container flex h-full w-full flex-col bg-black">
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
      <div className="border-b border-white/[0.08] px-[4cqw] pt-[1.6cqw] pb-[2.2cqw]">
        <div className="flex items-center justify-between text-white">
          <div className="flex size-[7.5cqw] items-center justify-center rounded-full bg-white/[0.08]">
            <HugeiconsIcon icon={ArrowLeft01Icon} strokeWidth={2} className="size-[4.2cqw] text-white/80" />
          </div>
          <div className="flex size-[7.5cqw] items-center justify-center rounded-full bg-white/[0.08]">
            <HugeiconsIcon icon={CameraVideoIcon} strokeWidth={1.8} className="size-[4.2cqw] text-white/80" />
          </div>
        </div>
        <div className="mt-[0.6cqw] flex flex-col items-center gap-[1.2cqw]">
          <div className="flex size-[10cqw] items-center justify-center rounded-full bg-[#0f2c22]">
            <LogoMark className="h-[5.4cqw] w-auto" />
          </div>
          <p className="text-[3.2cqw] font-semibold text-white">Closer AI</p>
        </div>
      </div>

      {/* message thread */}
      <div className="flex flex-1 flex-col gap-[1.2cqw] overflow-hidden px-[4cqw] pt-[2.4cqw] pb-[2.4cqw]">
        <p className="mb-[0.4cqw] text-center text-[2.4cqw] uppercase tracking-[0.1em] text-white/35">
          Today 2:14 PM
        </p>

        <Bubble from="me">"He says 6,400 is what it's worth — plenty of life left in it."</Bubble>
        <Bubble from="closer">Classic anchor, no real concession yet. Counter at $4,848.</Bubble>

        <div className="mt-[0.6cqw]">
          <Bubble from="me">"He came down to 5,900 and says that's already a favor."</Bubble>
        </div>
        <Bubble from="closer">That's a real $500 move. Counter at $4,992.</Bubble>

        <div className="mt-[0.6cqw]">
          <Bubble from="me">
            "He says three other people are coming to see it Saturday, so he's not moving."
          </Bubble>
        </div>
        <p className="pr-[1cqw] text-right text-[2.2cqw] text-white/35">Delivered</p>
        <Bubble from="closer">
          That's pressure, not a real move — the number barely budged. Hold at{" "}
          <span className="money font-semibold">$4,992</span>.
        </Bubble>
        <p className="money px-[1cqw] text-[2.4cqw] text-white/40">the curve moved $4 · bluff called</p>

        {/* input bar */}
        <div className="mt-auto pt-[1.6cqw] flex items-center gap-[2.4cqw]">
          <HugeiconsIcon icon={Add01Icon} strokeWidth={2} className="size-[6cqw] shrink-0 text-white/45" />
          <div className="flex flex-1 items-center justify-between rounded-full border border-white/15 py-[1.6cqw] pr-[2.4cqw] pl-[3.6cqw] text-[3cqw] text-white/35">
            <span>iMessage</span>
            <HugeiconsIcon icon={Mic01Icon} strokeWidth={2} className="size-[3.4cqw] shrink-0 text-white/40" />
          </div>
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
