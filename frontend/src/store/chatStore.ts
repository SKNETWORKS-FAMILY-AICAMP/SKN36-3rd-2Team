import { create } from 'zustand'
import { api, apiMode } from '../api/client'
import { ApiHttpError } from '../api/httpApi'
import type { Message } from '../api/types'
import { useGameStore } from './gameStore'

interface ChatStore {
  messages: Record<string, Message[]>
  loaded: Record<string, boolean>
  typing: string | null
  error: string | null
  canRetry: boolean
  load: (npcId: string) => Promise<void>
  send: (npcId: string, text: string) => Promise<void>
  present: (npcId: string, evidenceId: string, title: string) => Promise<void>
  retry: () => Promise<void>
}

let tmp = 0
let inFlight = false
let messageEpoch = 0
const local = (role: Message['role'], text: string): Message => ({
  id: `t${tmp++}`,
  role,
  text,
  at: Date.now(),
})

type Pending = {
  npcId: string
  playerText: string
  call: (sid: string) => ReturnType<typeof api.sendMessage>
}
let last: Pending | null = null

export const useChatStore = create<ChatStore>((set, get) => {
  const run = async (
    npcId: string,
    playerText: string,
    call: Pending['call'],
    isRetry = false,
  ) => {
    const sid = useGameStore.getState().session?.sessionId
    if (!sid || inFlight || get().typing) return

    // 전역 뮤텍스: 버튼·Enter·증거 제시에서 같은 턴이 동시에 전송되는 것을 차단합니다.
    inFlight = true
    ++messageEpoch
    last = { npcId, playerText, call }
    const current = get().messages[npcId] ?? []
    const outgoing = isRetry ? current : [...current, local('player', playerText)]
    set({
      messages: { ...get().messages, [npcId]: outgoing },
      typing: npcId,
      error: null,
      canRetry: false,
    })

    try {
      const reply = await call(sid)
      const saved = get().messages[npcId] ?? []
      ++messageEpoch
      set({
        messages: { ...get().messages, [npcId]: [...saved, local('npc', reply.reply)] },
        canRetry: false,
      })
      last = null

      // 답변은 이미 서버에 저장됐습니다. 이후 상태 조회 실패를 '대화 전송 실패'로
      // 처리하면 사용자가 다시 전송하여 중복 대화를 만들 수 있습니다.
      try {
        await useGameStore.getState().handleEvents(reply.events)
      } catch {
        set({ error: '답변은 저장됐지만 진행 상태 갱신에 실패했습니다. 새로고침하여 확인해 주세요.' })
      }
    } catch (error) {
      const isConflict = error instanceof ApiHttpError && error.status === 409
      const isHttp = apiMode === 'http'
      let recovered = false

      if (isHttp) {
        // 실패 응답을 받았더라도 서버가 이미 저장했을 수 있으므로 기록을 우선 조회합니다.
        try {
          const history = await api.getMessages(sid, npcId)
          ++messageEpoch
          set({ messages: { ...get().messages, [npcId]: history }, loaded: { ...get().loaded, [npcId]: true } })
          recovered = true
        } catch { /* 네트워크 단절 시 기존 말풍선을 보존합니다. */ }
        try { await useGameStore.getState().refresh() } catch { /* 세션 유지 */ }
      }

      const message = error instanceof Error ? error.message : '대화에 실패했습니다.'
      set({
        error: isConflict
          ? '다른 요청으로 게임 상태가 변경됐습니다. 기록을 새로 불러왔습니다. 질문을 확인한 뒤 다시 입력해 주세요.'
          : isHttp
            ? `${message} 요청이 서버에서 처리됐을 수 있으므로 자동 재전송하지 않습니다. 대화 기록을 확인해 주세요.`
            : message,
        // HTTP 타임아웃·409·502에서는 서버 커밋 여부가 불명확할 수 있어 재전송 금지
        canRetry: !isHttp,
      })
      if (isHttp && recovered) last = null
    } finally {
      inFlight = false
      set({ typing: null })
    }
  }

  return {
    messages: {},
    loaded: {},
    typing: null,
    error: null,
    canRetry: false,
    retry: async () => {
      if (last) await run(last.npcId, last.playerText, last.call, true)
    },
    async load(npcId) {
      const sid = useGameStore.getState().session?.sessionId
      if (!sid) return
      const epoch = messageEpoch
      try {
        const history = await api.getMessages(sid, npcId)
        // 늦게 끝난 이전 GET 응답이 최신 대화 말풍선을 덮지 못하도록 방지합니다.
        if (epoch === messageEpoch && !inFlight) {
          set({ messages: { ...get().messages, [npcId]: history } })
        }
      } catch {
        /* 기록 조회 실패만으로 새 대화까지 막지는 않습니다. */
      } finally {
        set({ loaded: { ...get().loaded, [npcId]: true } })
      }
    },
    send: (npcId, text) => run(npcId, text, (sid) => api.sendMessage(sid, npcId, text)),
    present: (npcId, evidenceId, title) => run(
      npcId,
      `[증거 제시] ${title}`,
      (sid) => api.presentEvidence(sid, npcId, evidenceId),
    ),
  }
})
