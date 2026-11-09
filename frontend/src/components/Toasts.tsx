import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Lock, FileSearch } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import styles from './Toasts.module.css'

export default function Toasts() {
  const toasts = useGameStore((s) => s.toasts)
  const dismiss = useGameStore((s) => s.dismissToast)
  const navigate = useNavigate()
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
            onClick={() => { dismiss(t.id); if (t.to) navigate(t.to) }}
          >
            {t.kind === 'evidence' ? <FileSearch size={16} /> : <Lock size={16} />}
            <span>{t.text}</span>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  )
}
