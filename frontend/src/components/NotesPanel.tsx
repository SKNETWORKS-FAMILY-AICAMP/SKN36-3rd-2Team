import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useNoteStore } from '../store/noteStore'
import Notebook from './Notebook'
import styles from './NotesPanel.module.css'

// 게임 중 어느 화면에서나 여는 추리 노트 패널 (메인·노트 화면 제외)
export default function NotesPanel() {
  const open = useNoteStore((s) => s.panelOpen)
  const setPanel = useNoteStore((s) => s.setPanel)
  const { pathname } = useLocation()
  const hidden = pathname === '/' || pathname === '/notes'
  return (
    <AnimatePresence>
      {open && !hidden && (
        <motion.aside
          className={styles.panel}
          role="complementary"
          aria-label="추리 노트"
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
        >
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
