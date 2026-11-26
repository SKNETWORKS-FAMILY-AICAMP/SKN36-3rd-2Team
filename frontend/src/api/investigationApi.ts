// 현장 조사 전용 API. 획득 조건과 점수는 서버에서만 판정합니다.
import { request } from './httpApi'

export interface InvestigationResult {
  evidenceId: string
  created: boolean
  score: number
  total: number
  revision: number
}

export async function investigate(sessionId: string, actionId: string): Promise<InvestigationResult> {
  const path = `/games/${encodeURIComponent(sessionId)}`
  const state = await request<{ revision: number }>(path)
  if (!Number.isInteger(state.revision) || state.revision < 0) {
    throw new Error('서버의 게임 상태를 확인할 수 없습니다.')
  }
  return request<InvestigationResult>(`${path}/investigations/${encodeURIComponent(actionId)}`, {
    method: 'POST',
    body: JSON.stringify({ expectedRevision: state.revision }),
  })
}
