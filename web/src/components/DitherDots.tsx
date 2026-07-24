import { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"

const SPACING = 24
const SQUARE_SIZE = 2.6
const MIN_SCALE = 0.5
const MAX_SCALE = 1.6
const MIN_ALPHA = 0.05
const MAX_ALPHA = 0.34
const SPEED = 0.0013

type Dot = { x: number; y: number; phase: number; speed: number }

export function DitherDots({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const container = canvas?.parentElement
    if (!canvas || !container) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    let dots: Dot[] = []
    let width = 0
    let height = 0

    const buildDots = () => {
      const cols = Math.ceil(width / SPACING) + 1
      const rows = Math.ceil(height / SPACING) + 1
      dots = []
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          dots.push({
            x: col * SPACING,
            y: row * SPACING,
            phase: Math.random() * Math.PI * 2,
            speed: 0.5 + Math.random() * 1.3,
          })
        }
      }
    }

    const resize = () => {
      width = container.clientWidth
      height = container.clientHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      buildDots()
    }

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height)
      for (const d of dots) {
        const wave = Math.sin(t * SPEED * d.speed + d.phase) * 0.5 + 0.5
        const alpha = MIN_ALPHA + wave * (MAX_ALPHA - MIN_ALPHA)
        const size = SQUARE_SIZE * (MIN_SCALE + wave * (MAX_SCALE - MIN_SCALE))
        ctx.fillStyle = `rgba(255,255,255,${alpha.toFixed(3)})`
        ctx.fillRect(d.x - size / 2, d.y - size / 2, size, size)
      }
    }

    const ro = new ResizeObserver(resize)
    ro.observe(container)
    resize()

    if (reduceMotion) {
      draw(0)
      return () => ro.disconnect()
    }

    let raf = 0
    const loop = (t: number) => {
      draw(t)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0", className)}
    />
  )
}
