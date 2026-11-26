import { useEffect, useRef } from 'react'
import { ShieldAlert } from 'lucide-react'
import styles from './ConsentModal.module.css'

// 민감한 기록을 열기 전 동의 모달 (화면만).
// 서버가 "동의 가능" 상태를 줄 때만 띄우고, 동의하면 서버 동의 API를 부른다. 필드 이름·API는 백엔드 명세가 오면 연결한다.
// 문구에는 기록 내용을 쓰지 않는다. 동의하지 않아도 게임은 그대로 진행된다.
export default function ConsentModal({ open, busy = false, error, onAgree, onDecline }: {
  open: boolean
  busy?: boolean
  error?: string | null
  onAgree: () => void
  onDecline: () => void
}) {
  const declineRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    declineRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onDecline() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onDecline])

  if (!open) return null
  return (
    <div className={styles.backdrop}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="consent-title" aria-describedby="consent-body">
        <h3 id="consent-title"><ShieldAlert size={18} />열람 전 확인</h3>
        <div id="consent-body" className={styles.body}>
          <p>다음 기록에는 사건 관계자의 개인적인 내용과, 읽는 사람에 따라 불편할 수 있는 표현이 담겨 있을 수 있습니다.</p>
          <p>열람하지 않아도 수사는 계속할 수 있고, 지금 선택은 이번 게임에만 적용됩니다.</p>
        </div>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <div className={styles.actions}>
          <button ref={declineRef} type="button" className="btn" onClick={onDecline} disabled={busy}>열람하지 않기</button>
          <button type="button" className={`btn ${styles.agree}`} onClick={onAgree} disabled={busy}>{busy ? '확인 중…' : '내용을 확인하고 열람'}</button>
        </div>
      </div>
    </div>
  )
}
