import { useEffect, useRef } from 'react'

interface Drop { x: number; y: number; len: number; speed: number; alpha: number }

/** 비 내리는 효과. prefers-reduced-motion 이면 그리지 않는다. */
export default function RainCanvas({ density = 1 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = 0
    let h = 0
    let raf = 0
    let drops: Drop[] = []

    const make = (): Drop => ({
      x: Math.random() * (w + 200) - 100,
      y: Math.random() * h,
      len: 10 + Math.random() * 22,
      speed: 14 + Math.random() * 14,
      alpha: 0.12 + Math.random() * 0.28,
    })

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round((w * h) / 9000 * density)
      drops = Array.from({ length: count }, make)
    }

    const tick = () => {
      ctx.clearRect(0, 0, w, h)
      ctx.lineWidth = 1
      for (const d of drops) {
        ctx.strokeStyle = `rgba(190, 205, 220, ${d.alpha})`
        ctx.beginPath()
        ctx.moveTo(d.x, d.y)
        ctx.lineTo(d.x - d.len * 0.22, d.y + d.len)
        ctx.stroke()
        d.y += d.speed
        d.x -= d.speed * 0.22
        if (d.y > h) {
          d.y = -d.len
          d.x = Math.random() * (w + 200) - 100
        }
      }
      raf = requestAnimationFrame(tick)
    }

    const onVisibility = () => {
      cancelAnimationFrame(raf)
      if (!document.hidden) raf = requestAnimationFrame(tick)
    }

    resize()
    raf = requestAnimationFrame(tick)
    window.addEventListener('resize', resize)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [density])

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  )
}
