import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { GROUP_PHOTO } from '../../data/characters'
import { GAME_TITLE } from '../../data/publicData'
import styles from './Reveal.module.css'

const GRID_W = 36
const GRID_H = 20
/** 이 비율 이상 지워지면 START 버튼을 강조한다 */
const EMPHASIS_AT = 0.07

/** 검은 막을 마우스로 지워 흐릿한 2016년 사진이 드러나는 시작 화면 */
export default function Reveal({ onStart, onResume }: { onStart: () => void; onResume?: () => void }) {
  const reduce = useReducedMotion()
  const rootRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const visited = useRef(new Set<number>())
  const last = useRef<{ x: number; y: number } | null>(null)
  const lastMove = useRef(performance.now())
  const [emphasis, setEmphasis] = useState(false)
  const [hint, setHint] = useState(false)

  const radius = () => Math.max(80, Math.min(150, window.innerWidth * 0.075))

  const markCoverage = useCallback((x: number, y: number, r: number) => {
    const root = rootRef.current
    if (!root) return
    const w = root.clientWidth
    const h = root.clientHeight
    const cx = Math.floor((x / w) * GRID_W)
    const cy = Math.floor((y / h) * GRID_H)
    const rx = Math.ceil((r / w) * GRID_W * 0.7)
    const ry = Math.ceil((r / h) * GRID_H * 0.7)
    for (let gy = cy - ry; gy <= cy + ry; gy++) {
      for (let gx = cx - rx; gx <= cx + rx; gx++) {
        if (gx < 0 || gy < 0 || gx >= GRID_W || gy >= GRID_H) continue
        visited.current.add(gy * GRID_W + gx)
      }
    }
    if (visited.current.size / (GRID_W * GRID_H) >= EMPHASIS_AT) setEmphasis(true)
  }, [])

  const stamp = useCallback((x: number, y: number) => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const r = radius()
    const g = ctx.createRadialGradient(x, y, 0, x, y, r)
    g.addColorStop(0, 'rgba(0,0,0,0.55)')
    g.addColorStop(0.55, 'rgba(0,0,0,0.3)')
    g.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.globalCompositeOperation = 'destination-out'
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fill()
    markCoverage(x, y, r)
  }, [markCoverage])

  const strokeTo = useCallback((x: number, y: number) => {
    const prev = last.current
    if (!prev) {
      stamp(x, y)
    } else {
      const dist = Math.hypot(x - prev.x, y - prev.y)
      const step = Math.max(6, radius() * 0.22)
      const n = Math.max(1, Math.ceil(dist / step))
      for (let i = 1; i <= n; i++) {
        stamp(prev.x + ((x - prev.x) * i) / n, prev.y + ((y - prev.y) * i) / n)
      }
    }
    last.current = { x, y }
  }, [stamp])

  // 캔버스 초기화(검은 막) + 크기 변경 시 지운 자국 유지
  useEffect(() => {
    const canvas = canvasRef.current
    const root = rootRef.current
    if (!canvas || !root) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let first = true

    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = root.clientWidth
      const h = root.clientHeight
      let snap: HTMLCanvasElement | null = null
      if (!first && canvas.width > 0) {
        snap = document.createElement('canvas')
        snap.width = canvas.width
        snap.height = canvas.height
        snap.getContext('2d')?.drawImage(canvas, 0, 0)
      }
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.globalCompositeOperation = 'source-over'
      if (snap) {
        ctx.drawImage(snap, 0, 0, w, h)
      } else {
        ctx.fillStyle = '#000'
        ctx.fillRect(0, 0, w, h)
      }
      first = false
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])

  // 마우스/터치 이동
  useEffect(() => {
    const root = rootRef.current
    if (!root || reduce) return
    const onMove = (e: PointerEvent) => {
      const rect = root.getBoundingClientRect()
      lastMove.current = performance.now()
      setHint(false)
      strokeTo(e.clientX - rect.left, e.clientY - rect.top)
    }
    root.addEventListener('pointermove', onMove)
    return () => root.removeEventListener('pointermove', onMove)
  }, [reduce, strokeTo])

  // 안내 문구(3초 뒤). 막은 플레이어가 직접 지울 때만 걷힌다
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    if (reduce) {
      setHint(true)
      // 움직임 줄이기: 처음부터 일부가 드러난 상태로 고정
      const w = root.clientWidth
      const h = root.clientHeight
      ;[[0.28, 0.45], [0.5, 0.55], [0.72, 0.45], [0.4, 0.3], [0.62, 0.7]].forEach(([fx, fy]) => {
        for (let i = 0; i < 4; i++) stamp(w * fx, h * fy)
      })
      return
    }
    const hintTimer = window.setTimeout(() => {
      if (performance.now() - lastMove.current > 2500) setHint(true)
    }, 1500)
    return () => window.clearTimeout(hintTimer)
  }, [reduce, stamp, strokeTo])

  return (
    <div ref={rootRef} className={styles.root}>
      <img className={styles.photo} src={GROUP_PHOTO} alt="" draggable={false} />
      <canvas ref={canvasRef} className={styles.mask} aria-hidden="true" />
      <div className={styles.content}>
        <div className={styles.titleBox}>
          <p className={styles.prefix}>{GAME_TITLE.prefix}</p>
          <h1 className={`serif ${styles.title}`}>{GAME_TITLE.main}</h1>
        </div>
        <div className={styles.bottom}>
          <p className={`${styles.hint} ${hint ? styles.hintOn : ''}`} aria-hidden={!hint}>
            {reduce ? '움직임 줄이기 설정이 켜져 있어 사진은 일부만 보입니다' : '마우스를 움직여 보세요'}
          </p>
          <button
            type="button"
            className={`${styles.start} ${emphasis ? styles.startOn : ''}`}
            onClick={onStart}
          >
            {onResume ? '새로 시작' : 'START'}
          </button>
          {onResume && (
            <button type="button" className={`${styles.start} ${styles.startOn}`} onClick={onResume}>
              이어하기
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
