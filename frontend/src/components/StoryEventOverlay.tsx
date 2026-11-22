import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  acknowledgeStoryEvent,
  getPendingStoryEvents,
  type PendingStoryEvent,
} from '../api/storyEventApi'
import { useGameStore } from '../store/gameStore'
import styles from './StoryEventOverlay.module.css'

interface EventQueue {
  sessionId: string
  items: PendingStoryEvent[]
}

interface DeferredEvents {
  sessionId: string
  eventKeys: string[]
}

export default function StoryEventOverlay() {
  const { pathname } = useLocation()

  const sessionId = useGameStore((s) => s.session?.sessionId)
  const revision = useGameStore((s) => s.session?.revision)
  const phase = useGameStore((s) => s.session?.phase)

  const [queue, setQueue] = useState<EventQueue | null>(null)
  const [deferred, setDeferred] = useState<DeferredEvents>({
    sessionId: '',
    eventKeys: [],
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  const busyRef = useRef(false)
  const dialogRef = useRef<HTMLDivElement>(null)

  // 메인·프롤로그·엔딩 화면에서는 사건 이벤트를 띄우지 않습니다.
  const enabled =
    Boolean(sessionId) &&
    phase === 'INVESTIGATION' &&
    pathname !== '/' &&
    pathname !== '/story' &&
    pathname !== '/final'

  useEffect(() => {
    if (!enabled || !sessionId) {
      setQueue(null)
      setError(null)
      return
    }

    let cancelled = false

    getPendingStoryEvents(sessionId)
      .then((items) => {
        if (cancelled) return
        setQueue({ sessionId, items })
        setError(null)
      })
      .catch(() => {
        if (cancelled) return
        setQueue(null)
        setError('사건 기록을 불러오지 못했습니다.')
      })

    return () => {
      cancelled = true
    }
  }, [enabled, sessionId, revision, pathname, retry])

  const items =
    queue && queue.sessionId === sessionId ? queue.items : []

  const deferredKeys =
    deferred.sessionId === sessionId ? deferred.eventKeys : []

  const current = enabled
    ? items.find((item) => !deferredKeys.includes(item.eventKey))
    : undefined

  // 모달이 열리면 포커스를 이동하고 배경 스크롤을 차단합니다.
  useEffect(() => {
    if (!current) return

    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow

    document.body.style.overflow = 'hidden'
    dialogRef.current
      ?.querySelector<HTMLButtonElement>('[data-primary]')
      ?.focus()

    return () => {
      document.body.style.overflow = previousOverflow
      if (previousFocus instanceof HTMLElement) {
        previousFocus.focus()
      }
    }
  }, [current?.eventKey])

  const defer = () => {
    if (!sessionId || !current || busyRef.current) return

    setDeferred((previous) => ({
      sessionId,
      eventKeys: [
        ...(previous.sessionId === sessionId
          ? previous.eventKeys
          : []),
        current.eventKey,
      ],
    }))
    setError(null)
  }

  const acknowledge = async () => {
    if (!sessionId || !current || busyRef.current) return

    const activeSession = sessionId
    const eventKey = current.eventKey

    busyRef.current = true
    setBusy(true)
    setError(null)

    try {
      await acknowledgeStoryEvent(activeSession, eventKey)

      // 다른 게임으로 이동한 사이의 응답을 새 세션에 적용하지 않습니다.
      if (
        useGameStore.getState().session?.sessionId !== activeSession
      ) {
        return
      }

      setQueue((previous) => {
        if (!previous || previous.sessionId !== activeSession) {
          return previous
        }

        return {
          sessionId: activeSession,
          items: previous.items.filter(
            (item) => item.eventKey !== eventKey,
          ),
        }
      })

      // ACK로 서버 revision이 증가했으므로 게임 상태를 동기화합니다.
      try {
        await useGameStore.getState().refresh()
      } catch {
        setError('기록 확인은 저장됐지만 진행 상태 갱신에 실패했습니다.')
      }
    } catch {
      if (
        useGameStore.getState().session?.sessionId === activeSession
      ) {
        setError('기록 확인에 실패했습니다. 다시 시도해 주세요.')
      }
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  if (!enabled) return null

  if (!current) {
    if (!error) return null

    return (
      <div className={styles.notice} role="status">
        <span>{error}</span>
        <button
          type="button"
          onClick={() => setRetry((value) => value + 1)}
        >
          다시 확인
        </button>
      </div>
    )
  }

  return (
    <div className={styles.backdrop}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="story-event-title"
        aria-describedby="story-event-text"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !busy) {
            defer()
          }

          if (event.key !== 'Tab') return

          const buttons = Array.from(
            dialogRef.current?.querySelectorAll<HTMLButtonElement>(
              'button:not(:disabled)',
            ) ?? [],
          )

          if (buttons.length === 0) {
            event.preventDefault()
            return
          }

          const first = buttons[0]
          const last = buttons[buttons.length - 1]

          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault()
            last.focus()
          } else if (
            !event.shiftKey &&
            document.activeElement === last
          ) {
            event.preventDefault()
            first.focus()
          }
        }}
      >
        <div className={styles.header}>
          <span className={styles.caseNo}>CASE 001</span>
          <span className={styles.chapter}>{current.chapter}</span>
        </div>

        <p className={styles.kicker}>새로운 사건 기록</p>

        <h2 id="story-event-title" className={styles.title}>
          {current.title}
        </h2>

        <div className={styles.rule} />

        <div
          id="story-event-text"
          className={styles.storyText}
        >
          {current.text}
        </div>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={defer}
            disabled={busy}
          >
            나중에 보기
          </button>

          <button
            type="button"
            data-primary
            className={styles.primary}
            onClick={() => void acknowledge()}
            disabled={busy}
          >
            {busy ? '기록 중…' : '확인하고 계속'}
          </button>
        </div>

        <p className={styles.hint}>
          나중에 보기를 선택하면 확인 처리되지 않습니다.
        </p>
      </div>
    </div>
  )
}
