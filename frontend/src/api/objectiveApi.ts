import { request } from './httpApi'

export interface ObjectiveItem {
  objectiveId: string
  status: string
}

export async function getObjectives(
  sessionId: string,
): Promise<ObjectiveItem[]> {
  const response = await request<{ items: ObjectiveItem[] }>(
    `/games/${encodeURIComponent(sessionId)}/objectives`,
  )
  return response.items
}

// 상세 목표 문구는 서버에서 제공해야 합니다.
// 서버 연동 전까지는 스포일러 없는 기본 안내를 사용합니다.
export function objectiveLabel(_id: string): string {
  return '현재 공개된 자료와 인물을 조사하세요.'
}

export function objectiveStatusLabel(status: string): string {
  switch (status.toUpperCase()) {
    case 'ACTIVE':
    case 'IN_PROGRESS':
    case 'AVAILABLE':
    case 'UNLOCKED':
      return '진행 중'
    case 'COMPLETE':
    case 'COMPLETED':
    case 'DONE':
      return '완료'
    default:
      return status
  }
}