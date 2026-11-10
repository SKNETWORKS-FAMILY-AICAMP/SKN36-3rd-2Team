import { create } from 'zustand'
import { api, apiMode } from '../api/client'
import { ApiHttpError } from '../api/httpApi'
import { isGameOver, type AccuseResponse, type EvidenceDetail, type GameEvent, type SessionState } from '../api/types'
import { CASE_INTRO } from '../mock/publicData'
import { npcName } from '../data/characters'
import { useNoteStore } from './noteStore'
import { useChatStore } from './chatStore'

const SID_KEY = 'serin-session-id'

export interface FinalRecord {
  suspectId: string
  evidenceIds: string[]
  sessionId?: string
  /** 종료 후 서버 조회가 막혀도 최종 화면에 제목을 보여주기 위해 지목 시점에 저장해 둔다 */
  evidenceTitles?: Record<string, string>
  response: AccuseResponse
}

const FINAL_KEY = 'serin-final-v1'
const LAST_ACCUSATION_KEY = 'serin-last-accusation-v1'

interface LastAccusation {
  sessionId: string
  suspectId: string
  evidenceIds: string[]
}

function loadLastAccusation(sessionId: string): LastAccusation | null {
  try {
    const raw = localStorage.getItem(LAST_ACCUSATION_KEY)
    if (!raw) return null
    const data: unknown = JSON.parse(raw)
    if (!data || typeof data !== 'object') return null
    const value = data as Partial<LastAccusation>
    if (value.sessionId !== sessionId || typeof value.suspectId !== 'string' ||
        !Array.isArray(value.evidenceIds) || !value.evidenceIds.every((id) => typeof id === 'string')) return null
    return value as LastAccusation
  } catch { return null }
}

function saveFinal(record: FinalRecord) {
  try { localStorage.setItem(FINAL_KEY, JSON.stringify(record)) } catch { /* ignore */ }
}
function loadFinal(): FinalRecord | null {
  try {
    const raw = localStorage.getItem(FINAL_KEY)
    if (!raw) return null
    const record = JSON.parse(raw) as FinalRecord
    const savedSessionId = localStorage.getItem(SID_KEY)
    return record.sessionId && record.sessionId !== savedSessionId ? null : record
  } catch { return null }
}

export interface Toast {
  id: number
  kind: 'evidence' | 'npc'
  text: string
  /** 눌렀을 때 이동할 화면 */
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
  accuse: (suspectId: string, evidenceIds: string[]) => Promise<AccuseResponse>
  recoverEnding: (state: SessionState) => Promise<void>
  resetGame: () => void
  startGame: () => Promise<void>
  /** 직접 주소로 들어온 경우: 저장된 세션을 이어받고, 없으면 새로 만든다 */
  ensureSession: () => Promise<void>
  refresh: () => Promise<void>
  loadEvidence: (id: string) => Promise<EvidenceDetail | null>
  handleEvents: (events: GameEvent[]) => Promise<void>
  dismissToast: (id: number) => void
}

let toastSeq = 1

const rememberSid = (id: string) => {
  try { localStorage.setItem(SID_KEY, id) } catch { /* ignore */ }
}

export const useGameStore = create<GameStore>((set, get) => ({
  session: null,
  notes: [],
  starting: false,
  accusing: false,
  endingError: null,
  evidence: {},
  toasts: [],
  // 실제 HTTP 모드의 결과는 브라우저 저장값이 아닌 서버 /ending에서 복구합니다.
  final: apiMode === 'http' ? null : loadFinal(),

  // ISSUE65_ENDING_INTEGRATION_V1: single submission and server-authoritative ending.
  async accuse(suspectId, evidenceIds) {
    const session = get().session
    if (!session) throw new Error('세션이 없습니다.')
    if (get().accusing) throw new Error('지목 결과를 처리하고 있습니다.')
    if (apiMode === 'http' && !session.canAccuse) throw new Error('아직 지목할 수 없습니다.')
    set({ accusing: true, endingError: null })
    try {
      // A lost HTTP response can still mean the server committed the accusation.
      // Keep the player's last selection for finished-session restoration.
      const last: LastAccusation = { sessionId: session.sessionId, suspectId, evidenceIds: [...evidenceIds] }
      try { localStorage.setItem(LAST_ACCUSATION_KEY, JSON.stringify(last)) } catch { /* ignore */ }

      const response = await api.accuse(session.sessionId, suspectId, evidenceIds)
      if (isGameOver(response)) {
        const titles: Record<string, string> = {}
        for (const id of evidenceIds) {
          const item = get().evidence[id] ?? (await get().loadEvidence(id))
          if (item) titles[id] = item.title
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
      try { await get().refresh() } catch { /* server already committed, do not resubmit */ }
      return response
    } catch (error) {
      // Never repeat a non-idempotent accusation automatically.
      try { await get().refresh() } catch { /* preserve last-known state */ }
      throw error
    } finally {
      set({ accusing: false })
    }
  },

  async recoverEnding(state) {
    if (apiMode !== 'http' || state.phase !== 'FINISHED') return
    try {
      const ending = await api.getEnding(state.sessionId)
      const previous = get().final?.sessionId === state.sessionId ? get().final : null
      const last = loadLastAccusation(state.sessionId)
      // The server owns the verdict; locally stored selections are only a display record.
      const record: FinalRecord = {
        sessionId: state.sessionId,
        suspectId: previous?.suspectId ?? last?.suspectId ?? '',
        evidenceIds: previous?.evidenceIds ?? last?.evidenceIds ?? [],
        evidenceTitles: previous?.evidenceTitles ?? {},
        response: {
          result: ending.outcome === 'SUCCESS' ? 'FULL' : 'WRONG',
          attemptsLeft: state.attemptsLeft,
          gameOver: true,
          ending: { title: ending.title, text: ending.message },
          endingKind: ending.deepEligible ? 'DEEP' : 'NORMAL',
          truth: ending.truth,
        },
      }
      set({ final: record, endingError: null })
      saveFinal(record)
    } catch (error) {
      set({ endingError: error instanceof Error ? error.message : '엔딩을 불러오지 못했습니다.' })
      // Keep any stored terminal result. GET /ending can be retried independently.
    }
  },

  resetGame() {
    try {
      localStorage.removeItem(FINAL_KEY)
      localStorage.removeItem(LAST_ACCUSATION_KEY)
      localStorage.removeItem(SID_KEY)
      localStorage.removeItem('serin-seen-places')
      localStorage.removeItem('serin-story-beat')
    } catch { /* ignore */ }
    useNoteStore.getState().clear()
    set({ session: null, final: null, evidence: {}, toasts: [], endingError: null, accusing: false })
  },

  async startGame() {
    if (get().starting) {
      throw new Error('이미 게임 생성 요청을 처리 중입니다.')
    }

    if (useChatStore.getState().typing !== null) {
      throw new Error('NPC 응답 처리 중에는 새 게임을 시작할 수 없습니다.')
    }

    set({ starting: true })

    try {
      // 기존 세션이 있어도 반드시 새 서버 세션을 생성합니다.
      const { state, notes } = await api.createSession()

      // 세션 생성에 성공한 뒤 이전 게임 데이터 초기화
      useChatStore.getState().clear()
      useNoteStore.getState().clear()
      useChatStore.getState().clear()

      try {
        localStorage.removeItem(FINAL_KEY)
        localStorage.removeItem(LAST_ACCUSATION_KEY)
        localStorage.removeItem('serin-seen-places')
        localStorage.removeItem('serin-story-beat')
      } catch {
        // 브라우저 저장소 접근 실패 시에도 메모리 초기화 진행
      }

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

  async ensureSession() {
    if (get().session || get().starting) return
    set({ starting: true })
    try {
      let sid: string | null = null
      try { sid = localStorage.getItem(SID_KEY) } catch { /* ignore */ }
      if (sid) {
        try {
          const state = await api.getState(sid)
          set({ session: state, notes: CASE_INTRO.notes, evidence: {}, toasts: [] })
          await get().recoverEnding(state)
          return
        } catch (error) {
          // HTTP 세션이 없을 때(404)에만 새 게임을 생성합니다.
          // 네트워크 장애 및 서버 오류는 기존 세션 ID를 유지합니다.
          if (
            apiMode === 'http' &&
            !(error instanceof ApiHttpError && error.status === 404)
          ) {
            throw error
          }
        }
      }
      const { state, notes } = await api.createSession()
      rememberSid(state.sessionId)
      // 저장된 세션을 못 찾아 새로 만드는 경우: 이전 게임의 기록이 섞이지 않게 비운다
      try {
        localStorage.removeItem(FINAL_KEY)
        localStorage.removeItem(LAST_ACCUSATION_KEY)
        localStorage.removeItem('serin-seen-places')
        localStorage.removeItem('serin-story-beat')
      } catch { /* ignore */ }
      useNoteStore.getState().clear()
      set({ session: state, notes, final: null, endingError: null })
    } finally {
      set({ starting: false })
    }
  },

  async refresh() {
    const s = get().session
    if (!s) return
    const state = await api.getState(s.sessionId)
    set({ session: state })
    await get().recoverEnding(state)
  },

  async loadEvidence(id) {
    const s = get().session
    if (!s) return null
    const hit = get().evidence[id]
    if (hit) return hit
    try {
      const d = await api.getEvidence(s.sessionId, id)
      set({ evidence: { ...get().evidence, [id]: d } })
      return d
    } catch {
      return null
    }
  },

  async handleEvents(events) {
    const s = get().session
    if (!s) return
    // NPC 답변에 알림 이벤트가 없어도 서버 상태를 동기화합니다.
    await get().refresh()
    if (events.length === 0) return
    const add: Toast[] = []
    const cache = { ...get().evidence }
    for (const ev of events) {
      if (ev.type === 'evidence_found') {
        try {
          const d = await api.getEvidence(s.sessionId, ev.id)
          cache[ev.id] = d
          add.push({ id: toastSeq++, kind: 'evidence', text: `새 증거를 확보했습니다 · ${d.title}`, to: '/evidence' })
        } catch {
          add.push({ id: toastSeq++, kind: 'evidence', text: '새 증거를 확보했습니다', to: '/evidence' })
        }
      } else if (ev.type === 'npc_unlocked') {
        add.push({ id: toastSeq++, kind: 'npc', text: `새로운 인물을 만날 수 있습니다 · ${npcName(ev.id)}`, to: `/chat/${ev.id}` })
      }
    }
    set({ evidence: cache, toasts: [...get().toasts, ...add] })
    for (const t of add) setTimeout(() => get().dismissToast(t.id), 5200)
  },

  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) })
  },
}))
