import { useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { NOTE_DEFAULT_W, NOTE_MIN_W, useNoteStore } from '../store/noteStore'
import Notebook from './Notebook'
import styles from './NotesPanel.module.css'

// 게임 중 어느 화면에서나 여는 추리 노트 패널 (메인 화면 제외). 추리 노트는 이 패널 하나뿐이다.
export default function NotesPanel({ docked = false }: { docked?: boolean } = {}) {
  const open = useNoteStore((s) => s.panelOpen)
  const setPanel = useNoteStore((s) => s.setPanel)
  const width = useNoteStore((s) => s.panelWidth)
  const setWidth = useNoteStore((s) => s.setPanelWidth)
  const drag = useRef<{ x: number; w: number } | null>(null)
  const { pathname } = useLocation()
  const hidden = pathname === '/' || (docked ? pathname !== '/play' : pathname === '/play')
  // Play에서는 별도 열을 사용하고, 기존 독립 화면에서는 고정 패널을 유지합니다.
  const resizeWidth = (next: number) => setWidth(docked
    ? Math.min(next, Math.floor(window.innerWidth * 0.4))
    : next)
  const actualWidth = (element: HTMLElement) => element.parentElement?.getBoundingClientRect().width ?? width
  if ((docked && pathname !== '/play') || (!docked && pathname === '/play')) return null
  return (
    <AnimatePresence>
      {open && !hidden && (
        <motion.aside
          className={`${styles.panel} ${docked ? styles.docked : ''}`}
          style={docked ? undefined : { width: `min(${width}px, 100vw)` }}
          role="complementary"
          aria-label="추리 노트"
          initial={docked ? false : { x: '100%' }}
          animate={{ x: 0 }}
          exit={docked ? undefined : { x: '100%' }}
          transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
        >
          <div
            className={styles.grip}
            role="separator"
            aria-orientation="vertical"
            aria-label="노트 폭 조절 (좌우 방향키)"
            aria-valuenow={docked ? Math.min(width, Math.floor(window.innerWidth * 0.4)) : width}
            aria-valuemin={NOTE_MIN_W}
            tabIndex={0}
            title="끌어서 폭 조절 · 더블클릭으로 원래 크기"
            onPointerDown={(e) => { drag.current = { x: e.clientX, w: actualWidth(e.currentTarget) }; e.currentTarget.setPointerCapture(e.pointerId) }}
            onPointerMove={(e) => { if (drag.current) resizeWidth(drag.current.w + (drag.current.x - e.clientX)) }}
            onPointerUp={() => { drag.current = null }}
            onPointerCancel={() => { drag.current = null }}
            onDoubleClick={() => resizeWidth(NOTE_DEFAULT_W)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowLeft') { e.preventDefault(); resizeWidth(actualWidth(e.currentTarget) + 40) }
              else if (e.key === 'ArrowRight') { e.preventDefault(); resizeWidth(actualWidth(e.currentTarget) - 40) }
            }}
          />
          <header>
            <h2 className="serif">수사관의 추리 노트</h2>
            <button type="button" onClick={() => setPanel(false)} aria-label="노트 닫기"><X size={18} /></button>
          </header>
          <Notebook compact />
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
