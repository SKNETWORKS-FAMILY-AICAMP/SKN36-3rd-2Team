/**
 * /play 통합 화면에 끼워 넣을 때 쓰는 공통 props.
 * embedded면 TopNav·Toasts 같은 공통 UI는 Play가 한 번만 그리고, 화면은 부모 칸 높이에 맞춘다.
 * onNpcSelect가 있으면 인물 이동을 주소 변경 대신 Play에 맡긴다. 기존 독립 화면 경로는 그대로 동작한다.
 */
export interface EmbedProps {
  embedded?: boolean
  onNpcSelect?: (npcId: string) => void
}
