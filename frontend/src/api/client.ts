import type {
  AccuseResponse, ChatReply, CreateSessionResponse, EvidenceDetail,
  Message, RelationGraph, SessionState, AvailableEvidence, GameEvent, EndingDetails,
} from './types'
import { mockApi } from './mockApi'
import { httpApi } from './httpApi'

export interface GameApi {
  createSession(): Promise<CreateSessionResponse>
  getState(sessionId: string): Promise<SessionState>
  getMessages(sessionId: string, npcId: string): Promise<Message[]>
  sendMessage(sessionId: string, npcId: string, text: string): Promise<ChatReply>
  presentEvidence(sessionId: string, npcId: string, evidenceId: string): Promise<ChatReply>
  getEvidence(sessionId: string, evidenceId: string): Promise<EvidenceDetail>
  getAvailableEvidence(sessionId: string): Promise<AvailableEvidence[]>
  collectEvidence(sessionId: string, evidenceId: string): Promise<GameEvent[]>
  getRelations(sessionId: string): Promise<RelationGraph>
  accuse(sessionId: string, suspectId: string, evidenceIds: string[]): Promise<AccuseResponse>
  getEnding(sessionId: string): Promise<EndingDetails>
}

const MODE_KEY = 'serin-api-mode'

/**
 * 연결 방식: 주소에 ?api=mock 또는 ?api=http 를 붙여 열면 그 방식을 브라우저에 기억해 빌드 없이 바꿀 수 있다.
 * (발표 중 서버가 안 될 때 mock으로 바로 전환: http://주소/?api=mock). 지정이 없으면 VITE_API_MODE.
 */
function pickMode(): 'mock' | 'http' {
  try {
    const q = new URLSearchParams(window.location.search).get('api')
    if (q === 'reset') localStorage.removeItem(MODE_KEY)
    if (q === 'mock' || q === 'http') {
      localStorage.setItem(MODE_KEY, q)
      return q
    }
    const saved = q === 'reset' ? null : localStorage.getItem(MODE_KEY)
    if (saved === 'mock' || saved === 'http') return saved
  } catch { /* 저장소를 못 쓰면 환경변수만 */ }
  return import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock'
}

export const apiMode = pickMode()

/** 기본은 VITE_API_MODE. ?api=mock|http 로 덮어쓸 수 있고, ?api=reset 은 지정을 지운다. */
export const api: GameApi = apiMode === 'http' ? httpApi : mockApi
