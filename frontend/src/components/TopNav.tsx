
import { useEffect, useState } from 'react'
import {
  NavLink,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import { CircleHelp, NotebookPen } from 'lucide-react'

import GameHelp from './GameHelp'
import { useGameStore } from '../store/gameStore'
import { useNoteStore } from '../store/noteStore'
import styles from './TopNav.module.css'

const HELP_SEEN_KEY = 'serin-help-seen-session-v2'

const ITEMS = [
  ['/story', '스토리'],
  ['/chat', '인물 대화'],
  ['/evidence', '증거 보관함'],
  ['/relations', '인물 관계도'],
  ['/accuse', '범인 지목'],
] as const

export default function TopNav() {
  const navigate = useNavigate()
  const location = useLocation()

  const toggle = useNoteStore((s) => s.setPanel)
  const noteOpen = useNoteStore((s) => s.panelOpen)

  const sessionId = useGameStore(
    (s) => s.session?.sessionId,
  )
  const phase = useGameStore(
    (s) => s.session?.phase,
  )
  const ended = useGameStore(
    (s) => !!s.final,
  )

  const [helpOpen, setHelpOpen] = useState(false)
  const [autoHelp, setAutoHelp] = useState(false)

  // 직접 인물 대화 화면으로 이동한 경우를 위한 보조 안내
  useEffect(() => {
    if (
      !location.pathname.startsWith('/chat') ||
      !sessionId ||
      phase === 'FINISHED'
    ) {
      return
    }

    try {
      if (localStorage.getItem(HELP_SEEN_KEY) === sessionId) {
        return
      }
    } catch {
      // 저장소를 사용할 수 없어도 안내합니다.
    }

    setAutoHelp(true)
    setHelpOpen(true)
  }, [location.pathname, sessionId, phase])

  const closeHelp = () => {
    // 자동으로 표시된 도움말만 확인 완료 처리
    if (autoHelp && sessionId) {
      try {
        localStorage.setItem(HELP_SEEN_KEY, sessionId)
      } catch {
        // 저장 실패 시에도 화면은 닫습니다.
      }
    }

    setAutoHelp(false)
    setHelpOpen(false)
  }

  return (
    <>
      <header className={styles.bar}>
        <NavLink
          to="/"
          className={styles.brand}
          aria-label="메인으로"
        >
          마지막 기록
          <em>졸업하지 못한 밤</em>
        </NavLink>

        <nav className={styles.nav} aria-label="화면 이동">
          {ITEMS.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `${styles.link} ${
                  isActive ? styles.active : ''
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => setHelpOpen(true)}
            aria-label="게임 도움말 열기"
            aria-haspopup="dialog"
          >
            <CircleHelp size={16} />
            <span className={styles.actionLabel}>
              도움말
            </span>
          </button>

          <button
            type="button"
            className="btn btn--sm"
            onClick={() => toggle(!noteOpen)}
            aria-label="추리 노트 열기"
            aria-pressed={noteOpen}
          >
            <NotebookPen size={16} />
            <span className={styles.actionLabel}>
              노트
            </span>
          </button>
        </div>
      </header>

      {ended && (
        <div className={styles.ended} role="status">
          수사가 종료되었습니다.
          서버에서 더 이상 조회되지 않는 자료가 있을 수 있습니다.

          <button
            type="button"
            className="btn btn--sm"
            onClick={() => navigate('/final')}
          >
            최종 화면 보기
          </button>
        </div>
      )}

      <GameHelp
        open={helpOpen}
        onClose={closeHelp}
      />
    </>
  )
}
