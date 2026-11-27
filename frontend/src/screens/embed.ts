/**
 * /play 통합 화면에 끼워 넣을 때 쓰는 공통 props.
 * embedded면 TopNav·Toasts 같은 공통 UI는 Play가 한 번만 그리고, 화면은 부모 칸 높이에 맞춘다.
 * onNpcSelect가 있으면 인물 이동을 주소 변경 대신 Play에 맡긴다. 기존 독립 화면 경로는 그대로 동작한다.
 */
export interface EmbedProps {
  embedded?: boolean
  onNpcSelect?: (npcId: string) => void
}

/** 통합 화면에서 알림을 눌렀을 때 Play가 열 대상 */
export type PlayTarget = { kind: 'evidence' } | { kind: 'npc'; npcId: string }

const PLAY_OPEN_EVENT = 'serin:play-open'

/** 알림 주소(/evidence, /chat/인물ID)를 통합 화면 대상으로 바꾼다. 해당 없으면 null */
export function playTargetOf(to: string): PlayTarget | null {
  if (to === '/evidence') return { kind: 'evidence' }
  const m = /^\/chat\/([^/]+)$/.exec(to)
  return m ? { kind: 'npc', npcId: m[1] } : null
}

/** 알림 → Play로 열 대상을 보낸다 (Toasts가 /play에서 사용) */
export function requestPlayOpen(target: PlayTarget) {
  window.dispatchEvent(new CustomEvent<PlayTarget>(PLAY_OPEN_EVENT, { detail: target }))
}

/**
 * Play에서 알림 대상을 받는다. 반환값은 구독 해제 함수.
 * 예) useEffect(() => onPlayOpen((t) => (t.kind === 'evidence' ? 증거함 팝업 열기 : selectNpc(t.npcId))), [])
 */
export function onPlayOpen(handler: (target: PlayTarget) => void) {
  const listener = (e: Event) => handler((e as CustomEvent<PlayTarget>).detail)
  window.addEventListener(PLAY_OPEN_EVENT, listener)
  return () => window.removeEventListener(PLAY_OPEN_EVENT, listener)
}
