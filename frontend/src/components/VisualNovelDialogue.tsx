import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

import CharacterPortrait from './CharacterPortrait'
import { NPC_PUBLIC } from '../data/characters'
import styles from './VisualNovelDialogue.module.css'

interface Props {
  chapter: string
  title?: string
  lines: readonly string[]
  progress: string
  storageKey?: string
  nextLabel?: string
  onNext: () => void
  onSkip?: () => void
}

function readPosition(key: string | undefined, count: number): number {
  if (!key || count < 1) return 0

  try {
    const value = Number(localStorage.getItem(key))
    if (!Number.isInteger(value)) return 0
    return Math.max(0, Math.min(value, count - 1))
  } catch {
    return 0
  }
}

export default function VisualNovelDialogue({
  chapter,
  title,
  lines,
  progress,
  storageKey,
  nextLabel = '다음 장면',
  onNext,
  onSkip,
}: Props) {
  const reducedMotion = useReducedMotion()

  const [index, setIndex] = useState(
    () => readPosition(storageKey, lines.length),
  )

  const [visible, setVisible] = useState(0)

  const raw = lines[index] ?? ''

  // 등록된 NPC 이름만 화자로 인식합니다.
  const speaker = NPC_PUBLIC.find(
    (npc) =>
      raw.startsWith(`${npc.name}:`) ||
      raw.startsWith(`${npc.name}：`),
  )

  const investigator = raw.startsWith('수사관:')
  const message = investigator ? raw.slice(4).trim() : speaker
    ? raw.slice(speaker.name.length + 1).trim()
    : raw

  useEffect(() => {
    if (reducedMotion) {
      setVisible(message.length)
      return
    }

    setVisible(0)
    let position = 0

    const timer = window.setInterval(() => {
      position = Math.min(position + 2, message.length)
      setVisible((current) => Math.max(current, position))

      if (position >= message.length) {
        window.clearInterval(timer)
      }
    }, 28)

    return () => window.clearInterval(timer)
  }, [index, message, reducedMotion])

  const advance = () => {
    if (visible < message.length) {
      setVisible(message.length)
      return
    }

    if (index < lines.length - 1) {
      const next = index + 1
      setIndex(next)

      if (storageKey) {
        try {
          localStorage.setItem(storageKey, String(next))
        } catch {
          // 저장 실패 시에도 진행은 계속합니다.
        }
      }

      return
    }

    onNext()
  }

  return (
    <section className={styles.root} aria-label="스토리 대화">
      <header className={styles.heading}>
        <p className={styles.chapter}>{chapter}</p>
        {title && <h2 className={styles.title}>{title}</h2>}
      </header>

      <div className={styles.stage}>
        {investigator && <img className={styles.portrait} alt="수사관" src={import.meta.env.BASE_URL + 'assets/characters/investigator.webp'} />}
        {speaker && (
          <motion.div
            key={speaker.id}
            className={styles.portraitWrap}
            initial={reducedMotion ? false : { opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.4 }}
          >
            <CharacterPortrait
              id={speaker.id}
              alt={speaker.name}
              standing
              className={styles.portrait}
            />
          </motion.div>
        )}
      </div>

      <div className={styles.dialogue}>
        <div className={styles.name}>
          {investigator ? '수사관' : speaker ? speaker.name : '기록'}
        </div>

        <button
          type="button"
          className={styles.message}
          onClick={advance}
          aria-label="대사 표시 또는 다음 대사"
        >
          <span aria-hidden="true">
            {message.slice(0, visible)}
            {visible < message.length && (
              <span className={styles.cursor}>▌</span>
            )}
          </span>
          <span className={styles.screenReader}>{message}</span>
        </button>

        <div className={styles.controls}>
          <span className={styles.progress}>
            {progress} · {index + 1}/{lines.length}
          </span>

          {onSkip && (
            <button
              type="button"
              className="scene-skip"
              onClick={onSkip}
            >
              건너뛰기
            </button>
          )}

          <button
            type="button"
            className={styles.next}
            onClick={advance}
          >
            {visible < message.length
              ? '대사 전체 보기'
              : index < lines.length - 1
                ? '다음 대사'
                : nextLabel}
          </button>
        </div>
      </div>
    </section>
  )
}
