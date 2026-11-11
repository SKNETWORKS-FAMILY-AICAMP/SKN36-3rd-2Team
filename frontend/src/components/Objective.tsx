import { Target } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { useChatStore } from '../store/chatStore'
import styles from './Objective.module.css'

/** 지금 무엇을 하면 좋은지 한 줄로 알려준다. 서버가 준 상태(증거 수·해금 인물·지목 가능 여부)만 사용하고 정답은 암시하지 않는다. */
export default function Objective() {
  const session = useGameStore((s) => s.session)
  const messages = useChatStore((s) => s.messages)
  if (!session) return null

  const unlocked = session.unlockedNpcs
  const found = session.foundEvidence.length
  const talked = unlocked.filter((id) => (messages[id]?.length ?? 0) > 0).length
  const untalked = unlocked.length - talked

  let text: string
  if (found === 0 && talked === 0) text = '인물에게 질문하여 첫 번째 단서를 확보하세요.'
  else if (found === 0) text = '아직 단서가 없습니다. 더 구체적으로 묻거나 다른 인물과도 이야기해 보세요.'
  else if (session.canAccuse) text = '단서가 모였습니다. 더 조사하거나 상단의 "범인 지목"으로 넘어갈 수 있습니다.'
  else if (untalked > 0) text = `아직 이야기를 듣지 않은 인물이 ${untalked}명 있습니다. 질문해 보세요.`
  else text = '확보한 증거를 "증거 제시"로 인물에게 보여 주고 반응을 살펴보세요. 새 증거와 인물이 열릴 수 있습니다.'

  return (
    <p className={styles.bar} role="note">
      <Target size={15} aria-hidden="true" />
      <b>현재 목표</b>
      <span>{text}</span>
    </p>
  )
}
