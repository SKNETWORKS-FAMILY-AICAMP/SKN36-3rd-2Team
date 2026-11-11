
import { create } from 'zustand'
import { api } from '../api/client'
import { ApiHttpError } from '../api/httpApi'
import {
  isGameOver,
  type AccuseResponse,
  type EvidenceDetail,
  type GameEvent,
  type SessionState,
} from '../api/types'
import { CASE_INTRO } from '../data/publicData'
import { npcName } from '../data/characters'
import { useNoteStore } from './noteStore'
import { useChatStore } from './chatStore'

const SID_KEY = 'serin-session-id'
const FINAL_KEY = 'serin-final-v1'
const LAST_ACCUSATION_KEY = 'serin-last-accusation-v1'

// Issue #59: 프롤로그 진행 상태 저장 키
const STORY_BEAT_KEY = 'serin-story-beat-v2'
const LEGACY_STORY_BEAT_KEY = 'serin-story-beat'
const SEEN_PLACES_KEY = 'serin-seen-places'

// ============================================================
// Types
// ============================================================

export interface FinalRecord {
  gaveUp?: boolean
  suspectId: string
  evidenceIds: string[]
  sessionId?: string

  /** 종료 후에도 최종 화면에 증거 제목을 표시하기 위한 기록 */
  evidenceTitles?: Record<string, string>

  response: AccuseResponse
}

interface LastAccusation {
  sessionId: string
  suspectId: string
  evidenceIds: string[]
}

export interface Toast {
  id: number
  kind: 'evidence' | 'npc'
  text: string
  to?: string
}

interface GameStore {
  session: SessionState | null
  notes: { id: string; text: string }[]

  starting: boolean
  accusing: boolean
  endingError: string | null

  evidence: Record<string, EvidenceDetail>
  toasts: Toast[]

  final: FinalRecord | null

  giveUp: (suspectId: string, response?: AccuseResponse) => void
  accuse: (
    suspectId: string,
    evidenceIds: string[],
  ) => Promise<AccuseResponse>

  recoverEnding: (state: SessionState) => Promise<void>

  resetGame: () => void
  startGame: () => Promise<void>
  ensureSession: () => Promise<void>
  refresh: () => Promise<void>

  loadEvidence: (
    id: string,
  ) => Promise<EvidenceDetail | null>

  handleEvents: (events: GameEvent[]) => Promise<void>

  dismissToast: (id: number) => void
}

let toastSeq = 1

// ============================================================
// Local Storage Helpers
// ============================================================

const rememberSid = (id: string): void => {
  try {
    localStorage.setItem(SID_KEY, id)
  } catch {
    // 브라우저 저장소를 사용할 수 없는 경우
  }
}

function loadLastAccusation(
  sessionId: string,
): LastAccusation | null {
  try {
    const raw = localStorage.getItem(LAST_ACCUSATION_KEY)

    if (!raw) return null

    const data: unknown = JSON.parse(raw)

    if (!data || typeof data !== 'object') {
      return null
    }

    const value = data as Partial<LastAccusation>

    if (
      value.sessionId !== sessionId ||
      typeof value.suspectId !== 'string' ||
      !Array.isArray(value.evidenceIds) ||
      !value.evidenceIds.every(
        (id) => typeof id === 'string',
      )
    ) {
      return null
    }

    return value as LastAccusation
  } catch {
    return null
  }
}

function saveFinal(record: FinalRecord): void {
  try {
    localStorage.setItem(
      FINAL_KEY,
      JSON.stringify(record),
    )
  } catch {
    // 저장 실패 시 메모리 상태는 유지합니다.
  }
}

/**
 * Issue #59
 * 프롤로그 및 현장 탐색 기록 초기화.
 *
 * 기존 v1 키와 새로운 v2 키를 모두 삭제합니다.
 */
function clearStoryProgress(): void {
  try {
    localStorage.removeItem(STORY_BEAT_KEY)
    localStorage.removeItem(LEGACY_STORY_BEAT_KEY)
    localStorage.removeItem(SEEN_PLACES_KEY)
  } catch {
    // 저장소를 사용할 수 없어도 게임 진행은 허용합니다.
  }
}

/**
 * 이전 게임의 브라우저 기록을 초기화합니다.
 * 서버 게임 상태나 판정 데이터는 직접 수정하지 않습니다.
 */
function clearSavedGame(): void {
  try {
    localStorage.removeItem(FINAL_KEY)
    localStorage.removeItem(LAST_ACCUSATION_KEY)
    localStorage.removeItem(SID_KEY)
  } catch {
    // 저장소 접근 실패 시에도 메모리 초기화를 진행합니다.
  }

  clearStoryProgress()
}

// ============================================================
// Zustand Game Store
// ============================================================

export const useGameStore = create<GameStore>((set, get) => ({
  session: null,
  notes: [],

  starting: false,
  accusing: false,
  endingError: null,

  evidence: {},
  toasts: [],

  // 실제 HTTP 모드의 엔딩은 서버에서 복구합니다.
  final: null,

  // ==========================================================
  // 범인 지목
  // ==========================================================

  giveUp(suspectId, previous) {
    const { session, final, accusing } = get()
    if (!session || final || accusing || session.phase === 'FINISHED') return
    const response: AccuseResponse = {
      result: previous?.result ?? 'NOT_ENOUGH_EVIDENCE',
      attemptsLeft: session.attemptsLeft, gameOver: true,
      ending: { title: '수사 종료', text: '남은 기회를 사용하지 않고 이번 조사를 마쳤습니다.' },
    }
    const record = { sessionId: session.sessionId, suspectId, evidenceIds: [...session.foundEvidence], response, gaveUp: true }
    saveFinal(record)
    set({ final: record })
  },

  async accuse(suspectId, evidenceIds) {
    const session = get().session

    if (!session) {
      throw new Error('세션이 없습니다.')
    }

    if (get().accusing) {
      throw new Error('지목 결과를 처리하고 있습니다.')
    }

    if (!session.canAccuse) {
      throw new Error('아직 지목할 수 없습니다.')
    }

    set({
      accusing: true,
      endingError: null,
    })

    try {
      // 응답 유실 시에도 마지막 지목 정보를 복구할 수 있도록 저장
      const last: LastAccusation = {
        sessionId: session.sessionId,
        suspectId,
        evidenceIds: [...evidenceIds],
      }

      try {
        localStorage.setItem(
          LAST_ACCUSATION_KEY,
          JSON.stringify(last),
        )
      } catch {
        // 저장 실패 시에도 지목 요청은 진행합니다.
      }

      const response = await api.accuse(
        session.sessionId,
        suspectId,
        evidenceIds,
      )

      if (isGameOver(response)) {
        const titles: Record<string, string> = {}

        for (const id of evidenceIds) {
          const item =
            get().evidence[id] ??
            (await get().loadEvidence(id))

          if (item) {
            titles[id] = item.title
          }
        }

        const record: FinalRecord = {
          sessionId: session.sessionId,
          suspectId,
          evidenceIds: [...evidenceIds],
          evidenceTitles: titles,
          response,
        }

        set({ final: record })
        saveFinal(record)
      }

      try {
        await get().refresh()
      } catch {
        // 서버가 이미 지목 결과를 반영했을 수 있으므로 재전송 금지
      }

      return response
    } catch (error) {
      // 지목 요청은 자동 재시도하지 않습니다.
      try {
        await get().refresh()
      } catch {
        // 마지막으로 확인된 게임 상태 유지
      }

      throw error
    } finally {
      set({ accusing: false })
    }
  },

  // ==========================================================
  // 엔딩 복구
  // ==========================================================

  async recoverEnding(state) {
    if (state.phase !== 'FINISHED') {
      return
    }

    try {
      const ending = await api.getEnding(state.sessionId)

      const previous =
        get().final?.sessionId === state.sessionId
          ? get().final
          : null

      const last = loadLastAccusation(state.sessionId)

      // 판정은 서버 응답만 신뢰합니다.
      const record: FinalRecord = {
        sessionId: state.sessionId,

        suspectId:
          previous?.suspectId ??
          last?.suspectId ??
          '',

        evidenceIds:
          previous?.evidenceIds ??
          last?.evidenceIds ??
          [],

        evidenceTitles:
          previous?.evidenceTitles ?? {},

        response: {
          result:
            ending.outcome === 'SUCCESS'
              ? ending.verdict ?? 'FULL'
              : 'WRONG',

          attemptsLeft: state.attemptsLeft,
          gameOver: true,

          ending: {
            title: ending.title,
            text: ending.message,
          },

          endingKind:
            ending.deepEligible
              ? 'DEEP'
              : 'NORMAL',

          truth: ending.truth,
          scene: ending.scene,
        },
      }

      set({
        final: record,
        endingError: null,
      })

      saveFinal(record)
    } catch (error) {
      set({
        endingError:
          error instanceof Error
            ? error.message
            : '엔딩을 불러오지 못했습니다.',
      })

      // 실패해도 기존 엔딩 결과는 유지합니다.
    }
  },

  // ==========================================================
  // 게임 초기화
  // ==========================================================

  resetGame() {
    // Issue #59: 스토리 기록까지 함께 초기화
    clearSavedGame()

    useNoteStore.getState().clear()

    set({
      session: null,
      notes: [],
      final: null,
      evidence: {},
      toasts: [],
      endingError: null,
      accusing: false,
    })
  },

  // ==========================================================
  // 새 게임 시작
  // ==========================================================

  async startGame() {
    if (get().starting) {
      throw new Error(
        '이미 게임 생성 요청을 처리 중입니다.',
      )
    }

    if (useChatStore.getState().typing !== null) {
      throw new Error(
        'NPC 응답 처리 중에는 새 게임을 시작할 수 없습니다.',
      )
    }

    set({ starting: true })

    try {
      // 기존 세션이 있어도 새로운 서버 세션을 생성합니다.
      const { state, notes } = await api.createSession()

      // 새 세션 생성에 성공한 경우에만 이전 기록 초기화
      useChatStore.getState().clear()
      useNoteStore.getState().clear()

      try {
        localStorage.removeItem(FINAL_KEY)
        localStorage.removeItem(LAST_ACCUSATION_KEY)
      } catch {
        // 메모리 상태 초기화는 계속 진행
      }

      // Issue #59: 프롤로그를 첫 장면부터 시작
      clearStoryProgress()

      rememberSid(state.sessionId)

      set({
        session: state,
        notes,
        evidence: {},
        toasts: [],
        final: null,
        endingError: null,
        accusing: false,
      })
    } finally {
      set({ starting: false })
    }
  },

  // ==========================================================
  // 기존 세션 복구 / 새 세션 생성
  // ==========================================================

  async ensureSession() {
    if (get().session || get().starting) {
      return
    }

    set({ starting: true })

    try {
      let sid: string | null = null

      try {
        sid = localStorage.getItem(SID_KEY)
      } catch {
        // 저장소 접근 불가
      }

      if (sid) {
        try {
          const state = await api.getState(sid)
          try {
            const saved = JSON.parse(localStorage.getItem(FINAL_KEY) ?? 'null')
            if (state.phase !== 'FINISHED' && saved?.gaveUp && saved.sessionId === sid &&
                ['NOT_ENOUGH_EVIDENCE','WRONG','ESTIMATED'].includes(saved.response?.result) && Array.isArray(saved.evidenceIds)) {
              set({ final: saved })
            }
          } catch { /* stale local record */ }

          set({
            session: state,
            notes: CASE_INTRO.notes,
            evidence: {},
            toasts: [],
          })

          await get().recoverEnding(state)

          return
        } catch (error) {
          // 세션이 없는 경우(404)에만 새 게임을 생성합니다.
          if (
            !(
              error instanceof ApiHttpError &&
              error.status === 404
            )
          ) {
            throw error
          }
        }
      }

      // 기존 서버 세션이 없으면 새로운 세션 생성
      const { state, notes } = await api.createSession()

      rememberSid(state.sessionId)

      try {
        localStorage.removeItem(FINAL_KEY)
        localStorage.removeItem(LAST_ACCUSATION_KEY)
      } catch {
        // 저장소 접근 불가 시에도 계속 진행
      }

      // Issue #59: 이전 프롤로그 진행 기록 제거
      clearStoryProgress()

      useNoteStore.getState().clear()

      set({
        session: state,
        notes,
        final: null,
        evidence: {},
        toasts: [],
        endingError: null,
      })
    } finally {
      set({ starting: false })
    }
  },

  // ==========================================================
  // 서버 게임 상태 동기화
  // ==========================================================

  async refresh() {
    const session = get().session

    if (!session) {
      return
    }

    const state = await api.getState(session.sessionId)

    set({ session: state })

    await get().recoverEnding(state)
  },

  // ==========================================================
  // 증거 상세 조회
  // ==========================================================

  async loadEvidence(id) {
    const session = get().session

    if (!session) {
      return null
    }

    const cached = get().evidence[id]

    if (cached) {
      return cached
    }

    try {
      const detail = await api.getEvidence(
        session.sessionId,
        id,
      )

      set({
        evidence: {
          ...get().evidence,
          [id]: detail,
        },
      })

      return detail
    } catch {
      return null
    }
  },

  // ==========================================================
  // 게임 이벤트 처리
  // ==========================================================

  async handleEvents(events) {
    const session = get().session

    if (!session) {
      return
    }

    // NPC 답변에 이벤트가 없어도 서버 상태 동기화
    await get().refresh()

    if (events.length === 0) {
      return
    }

    const add: Toast[] = []
    const cache = { ...get().evidence }

    for (const event of events) {
      if (event.type === 'evidence_found') {
        try {
          const detail = await api.getEvidence(
            session.sessionId,
            event.id,
          )

          cache[event.id] = detail

          add.push({
            id: toastSeq++,
            kind: 'evidence',
            text: `새 증거를 확보했습니다 · ${detail.title}`,
            to: '/evidence',
          })
        } catch {
          add.push({
            id: toastSeq++,
            kind: 'evidence',
            text: '새 증거를 확보했습니다',
            to: '/evidence',
          })
        }
      } else if (event.type === 'npc_unlocked') {
        add.push({
          id: toastSeq++,
          kind: 'npc',
          text: `새로운 인물을 만날 수 있습니다 · ${npcName(event.id)}`,
          to: `/chat/${event.id}`,
        })
      }
    }

    set({
      evidence: cache,
      toasts: [
        ...get().toasts,
        ...add,
      ],
    })

    for (const toast of add) {
      setTimeout(
        () => get().dismissToast(toast.id),
        5200,
      )
    }
  },

  // ==========================================================
  // 알림 제거
  // ==========================================================

  dismissToast(id) {
    set({
      toasts: get().toasts.filter(
        (toast) => toast.id !== id,
      ),
    })
  },
}))
