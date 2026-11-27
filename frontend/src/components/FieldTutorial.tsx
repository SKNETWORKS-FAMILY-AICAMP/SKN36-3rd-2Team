import { useLayoutEffect, useRef, useState } from 'react'
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

type Rect = { left: number; top: number; right: number; bottom: number }
type Placement = { left: number; top: number }
const GAP = 16
const ANCHOR_GAP = 24

// 실제 화면에서 보이는 부분만 강조합니다.
function visibleRect(element: Element): Rect | null {
  const rect = element.getBoundingClientRect()
  let left = Math.max(0, rect.left), top = Math.max(0, rect.top)
  let right = Math.min(window.innerWidth, rect.right), bottom = Math.min(window.innerHeight, rect.bottom)
  for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
    const style = getComputedStyle(parent)
    const bounds = parent.getBoundingClientRect()
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      left = Math.max(left, bounds.left); right = Math.min(right, bounds.right)
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      top = Math.max(top, bounds.top); bottom = Math.min(bottom, bounds.bottom)
    }
  }
  return right > left && bottom > top ? { left, top, right, bottom } : null
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + GAP && a.right > b.left - GAP && a.top < b.bottom + GAP && a.bottom > b.top - GAP
}

// 강조 대상뿐 아니라 입력 폼, 인물 목록, 주요 버튼을 피해서 배치합니다.
function findPlacement(width: number, height: number, blocked: Rect[], target: Rect | null): Placement | null {
  const vw = window.innerWidth, vh = window.innerHeight
  if (width + GAP * 2 > vw || height + GAP * 2 > vh) return null
  const clamp = (n: number, max: number) => Math.max(GAP, Math.min(n, max - GAP))
  const xs = [GAP, (vw - width) / 2, vw - width - GAP]
  const ys = [GAP, (vh - height) / 2, vh - height - GAP]
  for (const r of blocked) {
    xs.push(r.left - width - ANCHOR_GAP, r.right + ANCHOR_GAP)
    ys.push(r.top - height - ANCHOR_GAP, r.bottom + ANCHOR_GAP)
  }
  if (target) {
    xs.push((target.left + target.right - width) / 2)
    ys.push((target.top + target.bottom - height) / 2)
  }
  let best: Placement | null = null, bestScore = Infinity
  for (const x of xs) for (const y of ys) {
    const left = clamp(x, vw - width), top = clamp(y, vh - height)
    const box = { left, top, right: left + width, bottom: top + height }
    if (blocked.some((r) => overlaps(box, r))) continue
    // 강조 대상 가까이에 배치하고, 가능하면 같은 가로 또는 세로 축에 맞춥니다.
    // 중앙은 대상이 없는 단계에서만 기본 위치로 사용합니다.
    const cx = left + width / 2, cy = top + height / 2
    const tx = target ? (target.left + target.right) / 2 : vw / 2
    const ty = target ? (target.top + target.bottom) / 2 : vh / 2
    const dx = Math.abs(cx - tx), dy = Math.abs(cy - ty)
    const score = target
      ? Math.hypot(dx, dy) + Math.min(dx, dy) * 1.5
      : dx + dy
    if (score < bestScore) { best = { left, top }; bestScore = score }
  }
  return best
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
  const [hole, setHole] = useState<Rect | null>(null)
  const [placement, setPlacement] = useState<Placement | null>(null)
  const [docked, setDocked] = useState(false)
  const [paused, setPaused] = useState(false)
  const guideRef = useRef<HTMLElement>(null)
  const nextRef = useRef(onNext)
  nextRef.current = onNext

  useLayoutEffect(() => {
    let target: Element | null = null
    let frame = 0
    let fallback = false
    let viewport = `${window.innerWidth}:${window.innerHeight}`
    const sync = () => {
      // B의 증거 선택 팝업이 열려 있으면 조작을 가리지 않습니다.
      const dialog = document.querySelector('[role="dialog"][aria-label="증거 제시"]')
      const pause = Boolean(dialog && dialog.getClientRects().length)
      setPaused(pause)
      if (pause) { setHole(null); return }
      const candidates = Array.from(document.querySelectorAll(selector)).filter((el) => el.getClientRects().length > 0)
      const next = (step === 'save' ? candidates[candidates.length - 1] : candidates[0]) ?? null
      // 입력 안내에서는 입력창과 전송 버튼을 함께 강조합니다.
      const focus = step === 'input' ? next?.parentElement ?? next : next
      setAvailable(Boolean(next && !next.matches(':disabled')))
      if (focus !== target) {
        target?.classList.remove(styles.highlight)
        target = focus
        target?.classList.add(styles.highlight)
        if (target) {
          const rect = target.getBoundingClientRect()
          if (rect.top < 76 || rect.bottom > window.innerHeight - 12) target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        }
      }
      const rect = target ? visibleRect(target) : null
      setHole(rect)
      const currentViewport = `${window.innerWidth}:${window.innerHeight}`
      if (viewport !== currentViewport) { fallback = false; viewport = currentViewport }
      const panel = guideRef.current
      if (!panel) return
      if (fallback) return
      const protectedElements = Array.from(document.querySelectorAll(
        '[data-tutorial="field-place-list"], [data-tutorial="field-hotspot"], [data-tutorial="interview-notes"], [data-tutorial="interview-hint"], [data-tutorial="field-evidence"], [data-tutorial="interview-input"], [data-tutorial="interview-npc-list"], [data-tutorial="interview-present"], [data-tutorial="interview-picked"]',
      ))
      const page = panel.parentElement
      // 첫 번째 조사 지점만이 아니라 모든 조사 버튼과 오른쪽 도구를 보호합니다.
      if (page) protectedElements.push(...Array.from(page.querySelectorAll(
        '[data-tutorial="field-scene"] button, :scope > div > nav button, :scope > header button, [data-tutorial="interview-profile"] button, [data-tutorial="interview-chat"] button, main details summary',
      )))
      const input = document.querySelector('[data-tutorial="interview-input"]')
      const form = input?.closest('form')
      if (form) protectedElements.push(form)
      const header = panel.parentElement?.querySelector(':scope > header')
      if (header?.tagName === 'HEADER') protectedElements.push(header)
      const tools = panel.parentElement?.querySelector('[data-tutorial="field-evidence"]')?.closest('nav')
      if (tools) protectedElements.push(...Array.from(tools.querySelectorAll('button')))
      const blocked = protectedElements.map(visibleRect).filter((item): item is Rect => item !== null)
      if (rect) blocked.push(rect)
      const size = panel.getBoundingClientRect()
      if (size.height === 0) return
      const position = window.innerWidth < 640 ? null : findPlacement(Math.min(340, window.innerWidth - 24), size.height, blocked, rect)
      if (!position) {
        // 안전한 위치가 없으면 화면 위에 겹치지 않는 일반 안내 영역을 사용합니다.
        fallback = true
        setDocked(true)
        setPlacement(null)
      } else {
        setDocked(false)
        setPlacement(position)
      }
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; sync() }) }
    // 실제 NPC 선택 동작만 자동 진행합니다. 서버 응답이 필요한 단계는 수동 진행합니다.
    const handleClick = (event: MouseEvent) => {
      if (step !== 'npc' || !(event.target instanceof Element)) return
      const button = event.target.closest('button')
      if (button && !button.disabled && button.closest(selector)) nextRef.current()
    }
    setDocked(false)
    setPlacement(null)
    sync()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'hidden'] })
    const resize = new ResizeObserver(schedule)
    if (guideRef.current) resize.observe(guideRef.current)
    resize.observe(document.documentElement)
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)
    document.addEventListener('click', handleClick)
    return () => {
      observer.disconnect(); resize.disconnect()
      window.removeEventListener('resize', schedule)
      window.removeEventListener('scroll', schedule, true)
      document.removeEventListener('click', handleClick)
      cancelAnimationFrame(frame)
      target?.classList.remove(styles.highlight)
    }
  }, [selector, step])

  const mask = hole ? `M0 0H${window.innerWidth}V${window.innerHeight}H0Z M${Math.max(0, hole.left - 5)} ${Math.max(0, hole.top - 5)}H${Math.min(window.innerWidth, hole.right + 5)}V${Math.min(window.innerHeight, hole.bottom + 5)}H${Math.max(0, hole.left - 5)}Z` : ''
  return (
    <>
      {!paused && !docked && hole && <svg className={styles.spotlight} aria-hidden="true"><path d={mask} fillRule="evenodd" /></svg>}
      <aside ref={guideRef} hidden={paused} className={`${styles.guide} ${docked ? styles.docked : ''}`} style={docked ? undefined : placement ?? { visibility: 'hidden' }} aria-label={interview ? '면담 튜토리얼' : '현장 수사 튜토리얼'} aria-live="polite">
        <small>{interview ? '면담' : '현장'} 튜토리얼 · {index + 1} / {interview ? INTERVIEW_STEPS.length : 2}</small>
        <h3>{guide.title}</h3>
        <p>{guide.text}</p>
        {!available && <p className={styles.waiting}>{step === 'room' ? '면담 가능한 게임 상태에서 계속할 수 있습니다.' : '현재 화면에 해당 기능이 없거나 아직 사용할 수 없습니다.'}</p>}
        <div className={styles.controls}>
          {interview && <button type="button" onClick={onNext}>{nextInterviewTutorial(step) ? '다음 안내' : '안내 완료'}</button>}
          <button type="button" onClick={onSkip}>{interview ? '면담 안내 건너뛰기' : '현장 안내 건너뛰기'}</button>
        </div>
      </aside>
    </>
  )
}
