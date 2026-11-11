import { ESTIMATED_ENDS_GAME } from '../config'
// 프론트-백엔드 계약 타입. 서버가 상태를 소유하고, 프론트는 응답을 표시만 한다.
// 클라이언트는 evidence/flags/결과를 서버에 보고하지 않는다.

export type GameEventType = 'evidence_found' | 'npc_unlocked' | 'note_added'

export interface GameEvent {
  type: GameEventType
  id: string
}

export interface Collection {
  /** 서버가 계산한 수집 점수. 프론트는 계산하지 않는다 */
  score: number
  total: number
}

export interface SessionState {
  sessionId: string
  unlockedNpcs: string[]
  foundEvidence: string[]
  collection: Collection
  attemptsLeft: number
  /** 범인 지목 가능 여부는 서버 응답을 따른다 */
  canAccuse: boolean
  /** FastAPI에서 관리하는 게임 단계. Mock 호환을 위해 선택 필드로 유지합니다. */
  phase?: 'PROLOGUE' | 'INVESTIGATION' | 'ACCUSATION' | 'FINISHED'
  activeCharacterId?: string
  outcome?: string | null
  revision?: number
}

export interface Message {
  id: string
  role: 'player' | 'npc'
  text: string
  at: number
}

export interface ChatReply {
  reply: string
  events: GameEvent[]
}

export interface AvailableEvidence {
  evidenceId: string
  name: string
  score: number
}

export interface EvidenceDetail {
  id: string
  title: string
  body: string | null
  /**
   * (선택) 한 증거에 문서가 여러 개일 때(예: 가림본/원본). 2개 이상이면 탭으로 보여준다.
   * 없거나 1개면 title/body 를 그대로 쓴다. 서버가 지금 보여도 되는 문서만 내려준다.
   */
  documents?: { id: string; label: string; title: string; body: string }[]
  /** 보유 인물 */
  holderId: string
  /** 획득 경로 */
  acquiredBy: 'question' | 'present' | 'initial' | null
  /** 서버가 확인한 관계만 */
  confirmedRelations: { id: string; label: string }[]
}

export interface RelationGraph {
  nodes: { id: string; unlocked: boolean }[]
  edges: { id: string; source: string; target: string; label: string }[]
}

export type AccuseResult = 'FULL' | 'ESTIMATED' | 'WRONG' | 'NOT_ENOUGH_EVIDENCE'

export interface EndingTruth {
  perpetratorId: string
  motive: string
  causeOfDeath: string
  crimeMethod: string
}

export interface EndingLine { speaker: string; text: string; image?: string }
export interface EndingDetails {
  scene?: EndingLine[]
  verdict?: 'FULL' | 'ESTIMATED' 
  outcome: 'SUCCESS' | 'FAILURE'
  title: string
  message: string
  deepEligible: boolean
  /** 서버가 승리 판정한 이후에만 제공됩니다. */
  truth: EndingTruth | null
}

export interface AccuseResponse {
  scene?: EndingLine[]
  result: AccuseResult
  attemptsLeft: number
  /** 게임이 끝났는지. 마지막 기회를 써서 실패한 경우에도 true (ending이 비어 있어도 됨) */
  gameOver?: boolean
  ending?: { title: string; text: string }
  /** (선택) FULL 엔딩의 종류. 'DEEP' 이면 최종 화면을 심화 엔딩 연출로 보여준다. 없으면 일반 */
  endingKind?: 'NORMAL' | 'DEEP'
  /** 성공 엔딩에서만 반환되는 서버 검증 사실 */
  truth?: EndingTruth | null
}

/** 최종 화면으로 넘어가야 하는 응답인지 판단한다. 판정 자체는 서버 값만 쓴다. */
export const isGameOver = (r: AccuseResponse) =>
  !!r.ending || !!r.gameOver || r.attemptsLeft <= 0 || r.result === 'FULL' || (ESTIMATED_ENDS_GAME && r.result === 'ESTIMATED')

export interface CreateSessionResponse {
  state: SessionState
  notes: { id: string; text: string }[]
}
