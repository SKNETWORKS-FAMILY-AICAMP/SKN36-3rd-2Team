import { useEffect } from 'react'
import styles from './FieldTutorial.module.css'

export type FieldTutorialStep = 'inspect' | 'room'

const STEPS = {
  inspect: {
    selector: '[data-tutorial="field-hotspot"]',
    title: '현장 조사',
    text: '빛나는 조사 지점을 눌러 확대 화면을 살펴보세요. 확대 화면을 닫으면 다음 안내로 넘어갑니다.',
  },
  room: {
    selector: '[data-tutorial="field-interview"]',
    title: '면담실 이동',
    text: '면담실을 선택해 관계자에게 질문하세요. 면담이 가능한 게임 상태에서 이동할 수 있습니다.',
  },
} as const

export default function FieldTutorial({ step, onSkip }: {
  step: FieldTutorialStep
  onSkip: () => void
}) {
  const guide = STEPS[step]
  useEffect(() => {
    let target: Element | null = null
    const sync = () => {
      const next = document.querySelector(guide.selector)
      if (next !== target) {
        target?.classList.remove(styles.highlight)
        target = next
        target?.classList.add(styles.highlight)
        if (target) {
          const rect = target.getBoundingClientRect()
          if (rect.top < 76 || rect.bottom > window.innerHeight - 12) {
            target.scrollIntoView({ block: 'center', inline: 'nearest' })
          }
        }
      }
    }
    sync()
    // 장소 또는 세부 공간 변경으로 대상 요소가 교체될 수 있습니다.
    const observer = new MutationObserver(sync)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      target?.classList.remove(styles.highlight)
    }
  }, [guide.selector])

  return (
    <aside className={styles.guide} aria-label="현장 수사 튜토리얼" aria-live="polite">
      <small>현장 튜토리얼 · {step === 'inspect' ? '1' : '2'} / 2</small>
      <h3>{guide.title}</h3>
      <p>{guide.text}</p>
      <button type="button" onClick={onSkip}>현장 안내 건너뛰기</button>
    </aside>
  )
}
