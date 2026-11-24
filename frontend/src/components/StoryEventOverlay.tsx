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
  revision: number | undefined
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

  // 조사 단계에서만 스토리 이벤트를 표시합니다.
  const enabled =
    Boolean(sessionId) &&
    phase === 'INVESTIGATION' &&
    pathname !== '/' &&
    pathname !== '/story' &&
    pathname !== '/final'

  // 세션 및 revision 변경 시 승인된 이벤트를 다시 조회합니다.
  useEffect(() => {
    if (!enabled || !sessionId) {
      setQueue(null)
      setError(null)
      return
    }

    let cancelled = false

    setQueue(null)
    setError(null)

    getPendingStoryEvents(sessionId)
      .then((items) => {
        if (cancelled) return

        const latest = useGameStore.getState().session

        // 이전 세션 또는 revision의 응답은 폐기합니다.
        if (
          latest?.sessionId !== sessionId ||
          latest?.revision !== revision
        ) {
          return
        }

        setQueue({
          sessionId,
          revision,
          items,
        })
        setError(null)
      })
      .catch(() => {
        if (cancelled) return

        const latest = useGameStore.getState().session

        if (
          latest?.sessionId !== sessionId ||
          latest?.revision !== revision
        ) {
          return
        }

        setQueue(null)
        setError('사건 기록을 불러오지 못했습니다.')
      })

    return () => {
      cancelled = true
    }
  }, [enabled, sessionId, revision, pathname, retry])

  // 현재 세션 및 revision과 일치하는 이벤트만 표시합니다.
  const items =
    queue &&
    queue.sessionId === sessionId &&
    queue.revision === revision
      ? queue.items
      : []

  const deferredKeys =
    deferred.sessionId === sessionId
      ? deferred.eventKeys
      : []

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
  }, [current?.eventKey, sessionId])

  // 나중에 보기는 서버 ACK를 생성하지 않습니다.
  const defer = () => {
    if (!sessionId || !current || busyRef.current) return

    setDeferred((previous) => {
      const previousKeys =
        previous.sessionId === sessionId
          ? previous.eventKeys
          : []

      return {
        sessionId,
        eventKeys: [
          ...new Set([
            ...previousKeys,
            current.eventKey,
          ]),
        ],
      }
    })

    setError(null)
  }

  // 현재 이벤트 확인 및 서버 상태 동기화
  const acknowledge = async () => {
    if (!sessionId || !current || busyRef.current) return

    const activeSession = sessionId
    const activeRevision = revision
    const eventKey = current.eventKey

    const latest = useGameStore.getState().session

    if (
      latest?.sessionId !== activeSession ||
      latest?.revision !== activeRevision
    ) {
      setQueue(null)
      setRetry((value) => value + 1)
      return
    }

    busyRef.current = true
    setBusy(true)
    setError(null)

    try {
      await acknowledgeStoryEvent(
        activeSession,
        eventKey,
      )

      // 다른 게임으로 이동했다면 이전 응답을 적용하지 않습니다.
      if (
        useGameStore.getState().session?.sessionId !==
        activeSession
      ) {
        return
      }

      // ACK 이후 기존 이벤트 목록은 무효화합니다.
      setQueue(null)

      try {
        await useGameStore.getState().refresh()

        if (
          useGameStore.getState().session?.sessionId ===
          activeSession
        ) {
          setRetry((value) => value + 1)
        }
      } catch {
        if (
          useGameStore.getState().session?.sessionId ===
          activeSession
        ) {
          setError(
            '기록 확인은 저장됐지만 진행 상태 갱신에 실패했습니다.',
          )
        }
      }
    } catch {
      if (
        useGameStore.getState().session?.sessionId ===
        activeSession
      ) {
        setError(
          '기록 확인에 실패했습니다. 다시 시도해 주세요.',
        )
      }
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  // 조회 오류 또는 상태 갱신 실패 시 최신 상태부터 복구합니다.
  const retryPending = async () => {
    if (!sessionId || busyRef.current) return

    const activeSession = sessionId

    busyRef.current = true
    setBusy(true)
    setError(null)

    try {
      await useGameStore.getState().refresh()

      if (
        useGameStore.getState().session?.sessionId ===
        activeSession
      ) {
        setRetry((value) => value + 1)
      }
    } catch {
      if (
        useGameStore.getState().session?.sessionId ===
        activeSession
      ) {
        setError('진행 상태를 불러오지 못했습니다.')
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
          disabled={busy}
          onClick={() => void retryPending()}
        >
          {busy ? '확인 중…' : '다시 확인'}
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
            event.preventDefault()
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

          if (
            event.shiftKey &&
            document.activeElement === first
          ) {
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
          <span className={styles.caseNo}>
            CASE 001
          </span>

          <span className={styles.chapter}>
            {current.chapter}
          </span>
        </div>

        <p className={styles.kicker}>
          새로운 사건 기록
        </p>

        <h2
          id="story-event-title"
          className={styles.title}
        >
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
          <p
            className={styles.error}
            role="alert"
          >
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