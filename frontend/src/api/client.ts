import type {
  AccuseResponse, ChatReply, CreateSessionResponse, EvidenceDetail,
  Message, RelationGraph, SessionState, AvailableEvidence, GameEvent, EndingDetails, ReconstructionSelections,
} from './types'
import { httpApi } from './httpApi'

export interface GameApi {
  createSession(): Promise<CreateSessionResponse>
  getState(sessionId: string): Promise<SessionState>
  getMessages(sessionId: string, npcId: string): Promise<Message[]>
  sendMessage(sessionId: string, npcId: string, text: string): Promise<ChatReply>
  presentEvidence(sessionId: string, npcId: string, evidenceId: string, question?: string): Promise<ChatReply>
  getEvidence(sessionId: string, evidenceId: string): Promise<EvidenceDetail>
  getAvailableEvidence(sessionId: string): Promise<AvailableEvidence[]>
  collectEvidence(sessionId: string, evidenceId: string): Promise<GameEvent[]>
  getRelations(sessionId: string): Promise<RelationGraph>
  accuse(sessionId: string, suspectId: string, evidenceIds: string[]): Promise<AccuseResponse>
  getEnding(sessionId: string): Promise<EndingDetails>
  giveUp(sessionId: string): Promise<AccuseResponse>
  reconstruct(sessionId: string, selections: ReconstructionSelections): Promise<boolean>
  /** 힌트 1단계. 서버가 준 안내 문장만 돌려준다 */
  getHint(sessionId: string): Promise<string>
  /** 엔딩 이미지 주소 목록(게임 종료 후). 이미지 없는 엔딩은 빈 배열 */
  getEndingImages(sessionId: string): Promise<string[]>
}

export const api: GameApi = httpApi
