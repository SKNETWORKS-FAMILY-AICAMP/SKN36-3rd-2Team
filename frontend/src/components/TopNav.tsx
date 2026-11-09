import { NavLink, useNavigate } from 'react-router-dom'
import { NotebookPen } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { useNoteStore } from '../store/noteStore'
import styles from './TopNav.module.css'

const ITEMS = [
  ['/story', '스토리'],
  ['/chat', '인물 대화'],
  ['/evidence', '증거 보관함'],
  ['/relations', '인물 관계도'],
  ['/notes', '추리 노트'],
  ['/accuse', '범인 지목'],
] as const

export default function TopNav() {
  const toggle = useNoteStore((s) => s.setPanel)
  const open = useNoteStore((s) => s.panelOpen)
  const ended = useGameStore((s) => !!s.final)
  const navigate = useNavigate()
  return (
    <>
    <header className={styles.bar}>
      <NavLink to="/" className={styles.brand} aria-label="메인으로">
        마지막 기록 <em>졸업하지 못한 밤</em>
      </NavLink>
      <nav className={styles.nav} aria-label="화면 이동">
        {ITEMS.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <button type="button" className="btn btn--sm" onClick={() => toggle(!open)} aria-pressed={open}>
        <NotebookPen size={15} /> 노트
      </button>
    </header>
    {ended && (
      <div className={styles.ended} role="status">
        수사가 종료되었습니다. 서버에서 더 이상 조회되지 않는 자료가 있을 수 있습니다.
        <button type="button" className="btn btn--sm" onClick={() => navigate('/final')}>최종 화면 보기</button>
      </div>
    )}
    </>
  )
}
