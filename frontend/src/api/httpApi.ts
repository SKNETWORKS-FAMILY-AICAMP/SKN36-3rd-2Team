import type { GameApi } from './client'
import type {
  AccuseResponse,
  AvailableEvidence,
  GameEvent,
  ChatReply,
  CreateSessionResponse,
  EvidenceDetail,
  EndingDetails,
  Message,
  ReconstructionSelections,
  RelationGraph,
  SessionState,
} from './types'
import { endingToResponse } from './types'

// ============================================================
// Backend Response Types
// ============================================================

interface BackendEvent {
  type: string
  characterId?: string
  evidenceId?: string
}

interface BackendGameState {
  sessionId: string
  phase: 'PROLOGUE' | 'INVESTIGATION' | 'ACCUSATION' | 'FINISHED'
  activeCharacterId: string
  unlockedCharacters: string[]
  collection: {
    score: number
    total: number
  }
  canAccuse: boolean
  attemptsLeft: number
  outcome: string | null
  revision: number
  currentChapter?: string
  e30ConsentAvailable?: boolean
  e30ConsentGranted?: boolean
  events: BackendEvent[]
}

interface BackendEvidenceItem {
  evidenceId: string
  name: string
  score: number
  stage: string
}

interface BackendAvailableEvidence {
  items: AvailableEvidence[]
}

interface BackendEvidenceDetail {
  id: string
  title: string
  body: string | null
  holderId: string
  acquiredBy: 'question' | 'present' | 'initial' | null
  confirmedRelations: { id: string; label: string }[]
}

interface BackendEvidenceCollect {
  evidenceId: string
  created: boolean
  game: BackendGameState
}

interface BackendEvidenceList {
  items: BackendEvidenceItem[]
  collectedCount: number
  totalCount: number
}

interface BackendChatHistory {
  sessionId: string
  characterId: string
  messages: {
    userMessage: string
    displayText: string
  }[]
}

interface BackendChatReply {
  characterId: string
  display_text: string
  game: BackendGameState
}

interface BackendRelations {
  nodes: {
    id: string
    label: string
  }[]
  edges: {
    id: string
    sourceId: string
    targetId: string
    relation: string
  }[]
}

interface BackendAccuseResponse {
  verdict?: 'FULL' | 'ESTIMATED'
  result: 'CORRECT' | 'INCORRECT' | 'NOT_ENOUGH_EVIDENCE'
  attemptsLeft: number
  game: BackendGameState
}

// Server ending payload is declared centrally as EndingDetails.

// ============================================================
// Configuration
// ============================================================

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

const TIMEOUT_MS = 15_000

/** 서버가 한 번에 받는 제시 증거 수. 서버가 evidenceIds[]를 받으면 2로 올린다 */
export const SERVER_PRESENT_MAX = 1

const CHAT_TIMEOUT_MS =
  Number(import.meta.env.VITE_CHAT_TIMEOUT_MS) || 90_000

// ============================================================
// HTTP Client
// ============================================================
export class ApiHttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = 'ApiHttpError'
  }
}

export async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()

  const timer = setTimeout(
    () => controller.abort(),
    timeoutMs,
  )

  let response: Response

  try {
    response = await fetch(`${BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      ...init,
      signal: controller.signal,
    })
  } catch (error) {
    if (
      error instanceof DOMException &&
      error.name === 'AbortError'
    ) {
      throw new Error(
        '서버 응답 시간이 초과되었습니다. 다시 시도해 주세요.',
      )
    }

    throw new Error(
      '서버에 연결할 수 없습니다. FastAPI 실행 상태를 확인해 주세요.',
    )
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let message = ''

    try {
      const body = (await response.json()) as {
        message?: unknown
        detail?: unknown
      }

      const detail = body.message ?? body.detail

      if (typeof detail === 'string') {
        message = detail
      }
    } catch {
      // JSON이 아닌 오류 응답은 기본 메시지 사용
    }

    throw new ApiHttpError(
      message || `요청에 실패했습니다 (${response.status})`,
      response.status,
    )
  }

  return (await response.json()) as T
}

function post(body: unknown): RequestInit {
  return {
    method: 'POST',
    body: JSON.stringify(body),
  }
}

function gamePath(sessionId: string): string {
  return `/games/${encodeURIComponent(sessionId)}`
}

/** 서버 증거 사진 주소. 획득한 증거만 서버가 내려주고(아니면 404), 세션 쿠키로 확인한다 */
export function evidencePhotoUrl(sessionId: string, evidenceId: string, thumbnail = false): string {
  return `${BASE}${gamePath(sessionId)}/evidence/${encodeURIComponent(evidenceId)}/photo${thumbnail ? '?thumbnail=true' : ''}`
}

// ============================================================
// Response Adapters
// ============================================================

function toSessionState(
  game: BackendGameState,
  evidenceIds: string[],
  evidenceTotal?: number,
): SessionState {
  return {
    sessionId: game.sessionId,
    unlockedNpcs: game.unlockedCharacters,
    foundEvidence: evidenceIds,
    collection: game.collection,
    attemptsLeft: game.attemptsLeft,
    canAccuse: game.canAccuse,
    phase: game.phase,
    activeCharacterId: game.activeCharacterId,
    outcome: game.outcome,
    revision: game.revision,
    evidenceTotal,
    currentChapter: game.currentChapter,
    consentAvailable: game.e30ConsentAvailable ?? false,
    consentGranted: game.e30ConsentGranted ?? false,
  }
}

function toGameEvents(
  events: BackendEvent[],
): ChatReply['events'] {
  const result: ChatReply['events'] = []

  for (const event of events) {
    if (
      event.type === 'EVIDENCE_COLLECTED' &&
      event.evidenceId
    ) {
      result.push({
        type: 'evidence_found',
        id: event.evidenceId,
      })
    }

    if (
      event.type === 'NPC_UNLOCKED' &&
      event.characterId
    ) {
      result.push({
        type: 'npc_unlocked',
        id: event.characterId,
      })
    }
  }

  return result
}

// 같은 브라우저의 다른 탭에서도 동일 세션 대화를 동시에 요청하지 않습니다.
// Web Locks를 사용할 수 없는 환경에서는 서버 revision 검증이 최종 방어선입니다.
async function withSessionChatLock<T>(
  sessionId: string,
  task: () => Promise<T>,
): Promise<T> {
  if (typeof navigator === 'undefined' || !navigator.locks) return task()
  return navigator.locks.request(
    `serin-chat-${sessionId}`,
    { ifAvailable: true },
    (lock) => {
      if (!lock) throw new Error('이전 대화가 처리 중입니다. 완료된 뒤 다시 질문해 주세요.')
      return task()
    },
  )
}

// ============================================================
// NPC Selection
// ============================================================

async function ensureNpcSelected(
  sessionId: string,
  npcId: string,
): Promise<void> {
  const path = gamePath(sessionId)

  let game = await request<BackendGameState>(path)

  // 프롤로그가 완료되지 않은 경우 조사 단계로 전환
  // 오프닝 종료 시 명시적 호출은 별도로 유지
  if (game.phase === 'PROLOGUE') {
    game = await request<BackendGameState>(
      `${path}/prologue/complete`,
      { method: 'POST' },
    )
  }

  if (game.phase !== 'INVESTIGATION') {
    throw new Error('현재 NPC와 대화할 수 없는 단계입니다.')
  }

  if (!game.unlockedCharacters.includes(npcId)) {
    throw new Error('아직 해금되지 않은 인물입니다.')
  }

  if (game.activeCharacterId !== npcId) {
    await request<BackendGameState>(
      `${path}/characters/${encodeURIComponent(npcId)}/select`,
      { method: 'POST' },
    )
  }
}

// ============================================================
// Game API
// ============================================================

export const httpApi: GameApi = {
  // 프롤로그 완료 및 조사 단계 전환
  completePrologue: async (sessionId): Promise<void> => {
    const path = gamePath(sessionId)
    const game = await request<BackendGameState>(path)

    if (game.phase === 'INVESTIGATION') return

    if (game.phase !== 'PROLOGUE') {
      throw new Error('프롤로그를 완료할 수 없는 단계입니다.')
    }

    const result = await request<BackendGameState>(
      `${path}/prologue/complete`,
      { method: 'POST' },
    )

    if (result.phase !== 'INVESTIGATION') {
      throw new Error('조사 단계로 전환하지 못했습니다.')
    }
  },

  // ----------------------------------------------------------
  // 1. 게임 생성
  // ----------------------------------------------------------

  createSession: async (): Promise<CreateSessionResponse> => {
    const game = await request<BackendGameState>(
      '/games',
      { method: 'POST' },
    )

    // 증거함 칸 수(기존판 10, 확장판 30)를 알기 위해 전체 증거 수만 함께 받습니다.
    // 실패해도 게임 생성은 그대로 진행하고, 다음 상태 조회 때 다시 채워집니다.
    let evidenceTotal: number | undefined
    try {
      const evidence = await request<BackendEvidenceList>(`${gamePath(game.sessionId)}/evidence`)
      evidenceTotal = evidence.totalCount
    } catch {
      evidenceTotal = undefined
    }

    return {
      state: toSessionState(game, [], evidenceTotal),
      notes: [],
    }
  },

  // ----------------------------------------------------------
  // 2. 게임 상태 조회
  // ----------------------------------------------------------

  getState: async (
    sessionId: string,
  ): Promise<SessionState> => {
    const path = gamePath(sessionId)

    const [game, evidence] = await Promise.all([
      request<BackendGameState>(path),
      request<BackendEvidenceList>(`${path}/evidence`),
    ])

    return toSessionState(
      game,
      evidence.items.map((item) => item.evidenceId),
      evidence.totalCount,
    )
  },

  // ----------------------------------------------------------
  // 3. NPC 대화 기록
  // ----------------------------------------------------------

  getMessages: async (
    sessionId: string,
    npcId: string,
  ): Promise<Message[]> => {
    const path = gamePath(sessionId)

    const game = await request<BackendGameState>(path)

    if (game.phase === 'PROLOGUE') {
      return []
    }

    const history = await request<BackendChatHistory>(
      `${path}/chats/${encodeURIComponent(npcId)}`,
    )

    // 백엔드가 메시지 시각을 제공하지 않으므로 임시 표시 시각 사용
    const now = Date.now()

    return history.messages.flatMap((item, index): Message[] => [
      {
        id: `${npcId}-${index}-player`,
        role: 'player',
        text: item.userMessage,
        at: now + index * 2,
      },
      {
        id: `${npcId}-${index}-npc`,
        role: 'npc',
        text: item.displayText,
        at: now + index * 2 + 1,
      },
    ])
  },

  // ----------------------------------------------------------
  // 4. NPC 대화 전송
  // ----------------------------------------------------------

  sendMessage: async (
    sessionId: string,
    npcId: string,
    text: string,
  ): Promise<ChatReply> => withSessionChatLock(sessionId, async () => {
    if (!text.trim()) throw new Error('질문을 입력해 주세요.')
    await ensureNpcSelected(sessionId, npcId)
    const response = await request<BackendChatReply>(
      `${gamePath(sessionId)}/chat`,
      post({ question: text.trim(), presentedEvidenceId: null }),
      CHAT_TIMEOUT_MS,
    )
    return {
      reply: response.display_text,
      events: toGameEvents(response.game.events),
    }
  }),

  // ----------------------------------------------------------
  // 5. NPC에게 증거 제시
  // ----------------------------------------------------------

  presentEvidence: async (
    sessionId: string,
    npcId: string,
    evidenceIds: string[],
    question = '이 증거에 대해 설명해 주세요.',
  ): Promise<ChatReply> => withSessionChatLock(sessionId, async () => {
    // 서버는 아직 증거 1개(presentedEvidenceId)만 받는다. evidenceIds[]가 생기면 여기서 배열로 보낸다
    if (!evidenceIds.length || evidenceIds.length > SERVER_PRESENT_MAX) throw new Error('두 증거를 함께 제시하는 기능은 서버 준비 중입니다.')
    const [evidenceId] = evidenceIds
    await ensureNpcSelected(sessionId, npcId)
    const response = await request<BackendChatReply>(
      `${gamePath(sessionId)}/chat`,
      post({ question, presentedEvidenceId: evidenceId }),
      CHAT_TIMEOUT_MS,
    )
    return {
      reply: response.display_text,
      events: toGameEvents(response.game.events),
    }
  }),

  // ----------------------------------------------------------
  // 6. 증거 상세 조회
  // ----------------------------------------------------------

  getEvidence: async (
    sessionId: string,
    evidenceId: string,
  ): Promise<EvidenceDetail> => {
    // The server permits detailed metadata only for already-collected evidence.
    return request<BackendEvidenceDetail>(
      `${gamePath(sessionId)}/evidence/${encodeURIComponent(evidenceId)}`,
    )
  },

  getAvailableEvidence: async (sessionId): Promise<AvailableEvidence[]> => {
    const response = await request<BackendAvailableEvidence>(
      `${gamePath(sessionId)}/evidence/available`,
    )
    return response.items
  },

  collectEvidence: async (sessionId, evidenceId): Promise<GameEvent[]> => {
    const response = await request<BackendEvidenceCollect>(
      `${gamePath(sessionId)}/evidence/${encodeURIComponent(evidenceId)}/collect`,
      { method: 'POST' },
    )
    return toGameEvents(response.game.events)
  },

  // ----------------------------------------------------------
  // 7. 인물 관계도
  // ----------------------------------------------------------

  getRelations: async (
    sessionId: string,
  ): Promise<RelationGraph> => {
    const response = await request<BackendRelations>(
      `${gamePath(sessionId)}/relationships`,
    )

    return {
      nodes: response.nodes.map((node) => ({
        id: node.id,
        unlocked: true,
      })),

      edges: response.edges.map((edge) => ({
        id: edge.id,
        source: edge.sourceId,
        target: edge.targetId,
        label: edge.relation,
      })),
    }
  },

  // ----------------------------------------------------------
  // 8. 범인 지목 / 엔딩
  // ----------------------------------------------------------

  // ISSUE65_ENDING_INTEGRATION_V1
  getEnding: async (sessionId): Promise<EndingDetails> =>
    request<EndingDetails>(`${gamePath(sessionId)}/ending`),

  accuse: async (
    sessionId: string,
    suspectId: string,
    _evidenceIds: string[],
  ): Promise<AccuseResponse> => {
    const path = gamePath(sessionId)

    // 기존 프론트 인터페이스에는 evidenceIds가 있지만,
    // 실제 증거 판정은 백엔드의 저장된 GameState를 사용합니다.
    void _evidenceIds

    const game = await request<BackendGameState>(path)

    const response = await request<BackendAccuseResponse>(
      `${path}/accusations`,
      post({
        suspectId,
        expectedRevision: game.revision,
      }),
    )

    const gameOver = response.game.phase === 'FINISHED'

    const result: AccuseResponse = {
      result:
        response.result === 'CORRECT'
          ? response.verdict ?? 'FULL'
          : response.result === 'INCORRECT'
            ? 'WRONG'
            : 'NOT_ENOUGH_EVIDENCE',

      attemptsLeft: response.attemptsLeft,
      gameOver,
    }

    if (gameOver) {
      try {
        const ending = await request<EndingDetails>(
          `${path}/ending`,
        )

        return endingToResponse(ending, response.attemptsLeft)
      } catch {
        // 지목 결과는 이미 저장되었으므로 재지목하지 않습니다.
        // 엔딩 상세 조회는 별도 요청으로 재시도해야 합니다.
      }
    }

    return result
  },

  // 수사 포기 (확장판 서버 전용). 증거가 부족할 때만 서버가 받아 주고 '증거 부족' 엔딩으로 끝난다.
  giveUp: async (sessionId: string): Promise<AccuseResponse> => {
    const path = gamePath(sessionId)
    const game = await request<BackendGameState>(path)
    await request(`${path}/give-up`, post({ expectedRevision: game.revision }))
    const ending = await request<EndingDetails>(`${path}/ending`)
    return endingToResponse(ending, game.attemptsLeft)
  },

  // 민감 기록 열람 동의. 서버가 조건·권한을 확인하고, 409면 호출한 쪽에서 상태를 다시 읽는다
  giveConsent: async (sessionId: string): Promise<void> => {
    const path = gamePath(sessionId)
    const game = await request<BackendGameState>(path)
    await request(`${path}/consent`, post({ expectedRevision: game.revision, consent: true }))
  },

  // 엔딩 이미지 (게임 종료 후에만). 서버가 확정한 엔딩의 이미지만 순서대로 준다. url은 /api부터 시작하는 경로라 API 서버 주소와 합친다.
  getEndingImages: async (sessionId: string): Promise<string[]> => {
    const res = await request<{ images?: { index: number; url: string }[] }>(`${gamePath(sessionId)}/ending/images`)
    return (res.images ?? [])
      .sort((a, b) => a.index - b.index)
      .map((image) => (/^https?:/.test(BASE) ? new URL(image.url, BASE).href : image.url))
  },

  // 사건 재구성 (확장판 서버 전용). 정답 여부는 서버만 판정하고 accepted로만 알려 준다.
  reconstruct: async (sessionId: string, selections: ReconstructionSelections): Promise<boolean> => {
    const path = gamePath(sessionId)
    const game = await request<BackendGameState>(path)
    const res = await request<{ accepted: boolean }>(
      `${path}/reconstruction`,
      post({ expectedRevision: game.revision, selections }),
    )
    return res.accepted
  },

  // 힌트 1단계. 횟수·점수 차감 없고 게임 상태도 바꾸지 않는다. revision이 어긋나면(409) 상태를 다시 읽고 한 번만 재시도한다.
  getHint: async (sessionId: string): Promise<string> => {
    const path = gamePath(sessionId)
    const ask = async () => {
      const game = await request<BackendGameState>(path)
      return request<{ text: string }>(`${path}/agents/hint`, post({ expectedRevision: game.revision, level: 1 }))
    }
    try {
      return (await ask()).text
    } catch (error) {
      if (!(error instanceof ApiHttpError && error.status === 409)) throw error
      return (await ask()).text
    }
  },
}
