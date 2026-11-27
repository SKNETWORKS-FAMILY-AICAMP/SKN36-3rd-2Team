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
  /** 서버가 알려준 전체 증거 수(GET /evidence의 totalCount). 기존판 10, 확장판 30. 없으면 기본 칸 수를 쓴다 */
  evidenceTotal?: number
  /** 서버 현재 챕터(CH00~CH04). 재구성은 CH04에서만 열린다 */
  currentChapter?: string
  /** 민감 기록 열람 동의를 지금 요청할 수 있는지 / 이미 동의했는지 (서버 판단). 동의만으로 기록이 열리지는 않는다 */
  consentAvailable?: boolean
  consentGranted?: boolean
}

/** 사건 재구성 항목: 동기·접근·시간·은폐. 항목마다 보유 증거 2~3개, 3항목 이상 제출 */
export type ReconstructionAxis = 'motive' | 'access' | 'timeline' | 'coverup'
export type ReconstructionSelections = Partial<Record<ReconstructionAxis, string[]>>

/** 확장판 서버인지(기존판 증거 10개보다 많음). 포기·재구성은 확장판에서만 서버가 처리한다 */
export const isExpandedSession = (s?: SessionState | null) => (s?.evidenceTotal ?? 0) > 10

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
  /** 기존판: SUCCESS / FAILURE. 확장판: 엔딩 5종 코드를 그대로 보낸다 */
  outcome: 'SUCCESS' | 'FAILURE' | 'FULL' | 'ESTIMATED' | 'DEEP' | 'UNSOLVED' | 'NO_EVIDENCE'
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

/** 서버 엔딩(GET /ending)을 최종 화면용 응답으로 바꾼다. 지목·포기·새로고침 복구가 같이 쓴다. */
export function endingToResponse(ending: EndingDetails, attemptsLeft: number): AccuseResponse {
  const o = ending.outcome
  const result: AccuseResult =
    o === 'SUCCESS' ? ending.verdict ?? 'FULL'
      : o === 'FULL' || o === 'DEEP' ? 'FULL'
        : o === 'ESTIMATED' ? 'ESTIMATED'
          : o === 'NO_EVIDENCE' ? 'NOT_ENOUGH_EVIDENCE'
            : 'WRONG'
  return {
    result,
    attemptsLeft,
    gameOver: true,
    ending: { title: ending.title, text: ending.message },
    endingKind: o === 'DEEP' || (o === 'SUCCESS' && ending.deepEligible) ? 'DEEP' : 'NORMAL',
    truth: ending.truth,
    scene: ending.scene,
  }
}

/** 최종 화면으로 넘어가야 하는 응답인지 판단한다. 판정 자체는 서버 값만 쓴다. */
export const isGameOver = (r: AccuseResponse) =>
  !!r.ending || !!r.gameOver || r.attemptsLeft <= 0 || r.result === 'FULL' || (ESTIMATED_ENDS_GAME && r.result === 'ESTIMATED')

export interface CreateSessionResponse {
  state: SessionState
  notes: { id: string; text: string }[]
}
