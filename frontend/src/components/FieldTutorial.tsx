import { useEffect, useState } from 'react'
import styles from './FieldTutorial.module.css'

// 현장 조사 2단계와 B의 면담 화면 안내를 같은 컴포넌트에서 관리합니다.
const FIELD_STEPS = {
  inspect: {
    selector: '[data-tutorial="field-hotspot"]',
    title: '현장 조사',
    text: '빛나는 조사 지점을 눌러 확대 화면을 살펴보세요. 조사 버튼이 있으면 서버에서 결과를 확인합니다. 확대 화면을 닫으면 다음 안내로 넘어갑니다.',
  },
  room: {
    selector: '[data-tutorial="field-interview"]',
    title: '면담실 이동',
    text: '면담실을 선택해 관계자에게 질문하세요. 면담이 가능한 게임 상태에서 이동할 수 있습니다.',
  },
} as const

const INTERVIEW_STEPS = [
  { id: 'npc', selector: 'interview-npc-list', title: '면담 대상 선택', text: '왼쪽 면담 대상 목록에서 해금된 인물을 선택하세요.' },
  { id: 'profile', selector: 'interview-profile', title: '인물 정보 확인', text: '선택한 인물의 프로필을 확인하세요.' },
  { id: 'chat', selector: 'interview-chat', title: '대화 기록', text: '질문과 인물의 답변을 읽고 중요한 내용을 확인하세요.' },
  { id: 'input', selector: 'interview-input', title: '질문하기', text: '질문을 입력하고 Enter로 전송하세요. Shift+Enter는 줄바꿈입니다.' },
  { id: 'collect', selector: 'interview-collect', title: '증거 확보', text: '새로운 단서를 확보할 수 있을 때 나타나는 확보 버튼을 누르세요. 확보 여부는 서버 결과를 따릅니다.' },
  { id: 'save', selector: 'interview-save-statement', title: '진술 저장', text: '대답에 마우스를 올리면 핀으로 진술을 저장할 수 있어요. 저장한 진술은 수사 기록에서 확인할 수 있습니다.' },
  { id: 'present', selector: 'interview-present', title: '증거 제시', text: '증거 제시 버튼을 눌러 확보한 증거를 선택하세요. 현재 서버에서는 한 번에 증거 1개를 제시할 수 있습니다.' },
  { id: 'picked', selector: 'interview-picked', title: '선택한 증거 확인', text: '입력창 위에 붙은 증거를 확인하세요. 질문을 함께 작성하거나 그대로 제시할 수 있습니다.' },
  { id: 'notes', selector: 'interview-notes', title: '수사 기록', text: '오른쪽 수사 기록에서 저장한 진술을 확인하고 자신의 추리를 적으세요.' },
  { id: 'hint', selector: 'interview-hint', title: '목표 · 힌트', text: '상단 목표 · 힌트를 열어 현재 목표를 확인하고 필요하면 힌트 확인 버튼으로 서버에 1단계 힌트를 요청하세요. 응답은 같은 팝업에서 확인합니다.' },
] as const

type InterviewStep = (typeof INTERVIEW_STEPS)[number]['id']
export type FieldTutorialStep = keyof typeof FIELD_STEPS | InterviewStep

export function isInterviewTutorial(step: FieldTutorialStep | null): step is InterviewStep {
  return INTERVIEW_STEPS.some((item) => item.id === step)
}

export function nextInterviewTutorial(step: InterviewStep): InterviewStep | null {
  const index = INTERVIEW_STEPS.findIndex((item) => item.id === step)
  return INTERVIEW_STEPS[index + 1]?.id ?? null
}

export default function FieldTutorial({ step, onSkip, onNext }: {
  step: FieldTutorialStep
  onSkip: () => void
  onNext: () => void
}) {
  const interview = isInterviewTutorial(step)
  const index = interview ? INTERVIEW_STEPS.findIndex((item) => item.id === step) : step === 'inspect' ? 0 : 1
  const guide = interview ? INTERVIEW_STEPS[index] : FIELD_STEPS[step]
  const selector = interview ? `[data-tutorial="${guide.selector}"]` : guide.selector
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    let target: Element | null = null
    const sync = () => {
      const candidates = Array.from(document.querySelectorAll(selector)).filter((el) => el.getClientRects().length > 0)
      // 여러 답변이 있으면 가장 최근 NPC 답변의 핀을 안내합니다.
      const next = (step === 'save' ? candidates[candidates.length - 1] : candidates[0]) ?? null
      setAvailable(Boolean(next && !next.matches(':disabled')))
      if (next !== target) {
        target?.classList.remove(styles.highlight)
        target = next
        target?.classList.add(styles.highlight)
        if (target) {
          const rect = target.getBoundingClientRect()
          if (rect.top < 76 || rect.bottom > window.innerHeight - 12) {
            target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
          }
        }
      }
    }
    sync()
    const observer = new MutationObserver(sync)
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'hidden'] })
    return () => {
      observer.disconnect()
      target?.classList.remove(styles.highlight)
    }
  }, [selector, step])

  return (
    <aside className={`${styles.guide} ${interview && step !== 'npc' ? styles.interviewGuide : ''}`} aria-label={interview ? '면담 튜토리얼' : '현장 수사 튜토리얼'} aria-live="polite">
      <small>{interview ? '면담' : '현장'} 튜토리얼 · {index + 1} / {interview ? INTERVIEW_STEPS.length : 2}</small>
      <h3>{guide.title}</h3>
      <p>{guide.text}</p>
      {!available && <p className={styles.waiting}>{step === 'room' ? '면담 가능한 게임 상태에서 계속할 수 있습니다.' : '현재 화면에 해당 기능이 없거나 아직 사용할 수 없습니다.'}</p>}
      {interview && <button type="button" onClick={onNext}>{nextInterviewTutorial(step) ? '다음 안내' : '안내 완료'}</button>}
      <button type="button" onClick={onSkip}>{interview ? '면담 안내 건너뛰기' : '현장 안내 건너뛰기'}</button>
    </aside>
  )
}
