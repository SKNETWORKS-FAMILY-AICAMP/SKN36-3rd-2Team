import { useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Lock, FileSearch } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { playTargetOf, requestPlayOpen } from '../screens/embed'
import styles from './Toasts.module.css'

export default function Toasts() {
  const toasts = useGameStore((s) => s.toasts)
  const dismiss = useGameStore((s) => s.dismissToast)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // 통합 화면(/play)에서는 페이지를 옮기지 않고 Play가 증거함 팝업·인물 면담을 연다
  const open = (to: string) => {
    const target = pathname === '/play' ? playTargetOf(to) : null
    if (target) requestPlayOpen(target)
    else navigate(to)
  }
  return (
    <div className={styles.wrap} role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.button
            key={t.id}
            type="button"
            className={`${styles.toast} ${t.kind === 'evidence' ? styles.ev : styles.npc}`}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.35 }}
            onClick={() => { dismiss(t.id); if (t.to) open(t.to) }}
          >
            {t.kind === 'evidence' ? <FileSearch size={16} /> : <Lock size={16} />}
            <span>{t.text}</span>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  )
}
