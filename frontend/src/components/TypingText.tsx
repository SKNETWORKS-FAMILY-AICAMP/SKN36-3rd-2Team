import { useEffect, useState } from 'react'

const reduceMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * 인물 답변 타이핑 효과. 약 2.5초 안에 끝나도록 한 번에 여러 글자씩 늘린다.
 * 누르면 바로 전체를 보여 준다. 동작 줄이기 설정이면 효과 없이 전체를 보여 준다.
 */
export default function TypingText({ text, onTick, onDone }: { text: string; onTick?: () => void; onDone?: () => void }) {
  const [n, setN] = useState(() => (reduceMotion() ? text.length : 0))
  const done = n >= text.length

  useEffect(() => {
    if (done) { onDone?.(); return }
    const step = Math.max(1, Math.ceil(text.length / 80))
    const t = setTimeout(() => { setN((v) => Math.min(text.length, v + step)); onTick?.() }, 30)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, done, text])

  return (
    <span onClick={() => setN(text.length)} title={done ? undefined : '눌러서 바로 보기'}>
      {text.slice(0, n)}
    </span>
  )
}
