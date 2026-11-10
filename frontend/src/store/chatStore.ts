
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

  clear: () => void
  load: (npcId: string) => Promise<void>
  send: (npcId: string, text: string) => Promise<void>
  present: (
    npcId: string,
    evidenceId: string,
    title: string,
  ) => Promise<void>
  retry: () => Promise<void>
}

let tmp = 0
let inFlight = false
let messageEpoch = 0
let sessionEpoch = 0
let activeRunEpoch = 0

const local = (
  role: Message['role'],
  text: string,
): Message => ({
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

    inFlight = true

    const currentRun = ++activeRunEpoch
    const currentSession = sessionEpoch

    ++messageEpoch

    // 이전 게임의 비동기 응답은 현재 게임에 반영하지 않습니다.
    const isCurrent = () =>
      currentSession === sessionEpoch &&
      currentRun === activeRunEpoch &&
      useGameStore.getState().session?.sessionId === sid

    last = { npcId, playerText, call }

    const current = get().messages[npcId] ?? []
    const outgoing = isRetry
      ? current
      : [...current, local('player', playerText)]

    set({
      messages: {
        ...get().messages,
        [npcId]: outgoing,
      },
      typing: npcId,
      error: null,
      canRetry: false,
    })

    try {
      const reply = await call(sid)

      if (!isCurrent()) return

      const saved = get().messages[npcId] ?? []

      ++messageEpoch

      set({
        messages: {
          ...get().messages,
          [npcId]: [
            ...saved,
            local('npc', reply.reply),
          ],
        },
        canRetry: false,
      })

      last = null

      // 답변은 서버에 저장됐으므로 자동 재전송하지 않습니다.
      try {
        await useGameStore.getState().handleEvents(reply.events)
      } catch {
        if (isCurrent()) {
          set({
            error:
              '답변은 저장됐지만 진행 상태 갱신에 실패했습니다. 새로고침하여 확인해 주세요.',
          })
        }
      }
    } catch (error) {
      if (!isCurrent()) return

      const isConflict =
        error instanceof ApiHttpError && error.status === 409

      const isHttp = apiMode === 'http'
      let recovered = false

      if (isHttp) {
        // 요청이 이미 처리됐을 가능성이 있으므로 서버 기록을 조회합니다.
        try {
          const history = await api.getMessages(sid, npcId)

          if (!isCurrent()) return

          ++messageEpoch

          set({
            messages: {
              ...get().messages,
              [npcId]: history,
            },
            loaded: {
              ...get().loaded,
              [npcId]: true,
            },
          })

          recovered = true
        } catch {
          // 네트워크 단절 시 기존 화면 상태를 유지합니다.
        }

        if (!isCurrent()) return

        try {
          await useGameStore.getState().refresh()
        } catch {
          // 마지막으로 확인된 세션 상태를 유지합니다.
        }
      }

      if (!isCurrent()) return

      const message =
        error instanceof Error
          ? error.message
          : '대화에 실패했습니다.'

      set({
        error: isConflict
          ? '다른 요청으로 게임 상태가 변경됐습니다. 기록을 새로 불러왔습니다. 질문을 확인한 뒤 다시 입력해 주세요.'
          : isHttp
            ? `${message} 요청이 서버에서 처리됐을 수 있으므로 자동 재전송하지 않습니다. 대화 기록을 확인해 주세요.`
            : message,
        canRetry: !isHttp,
      })

      if (isHttp && recovered) {
        last = null
      }
    } finally {
      // 이전 요청이 새 게임의 전송 상태를 변경하지 못하도록 합니다.
      if (currentRun === activeRunEpoch) {
        inFlight = false

        if (currentSession === sessionEpoch) {
          set({ typing: null })
        }
      }
    }
  }

  return {
    messages: {},
    loaded: {},
    typing: null,
    error: null,
    canRetry: false,

    // 새 게임 시작 시 이전 게임의 모든 채팅 상태를 초기화합니다.
    clear() {
      ++messageEpoch
      ++sessionEpoch
      ++activeRunEpoch

      inFlight = false
      last = null
      tmp = 0

      set({
        messages: {},
        loaded: {},
        typing: null,
        error: null,
        canRetry: false,
      })
    },

    retry: async () => {
      if (last) {
        await run(
          last.npcId,
          last.playerText,
          last.call,
          true,
        )
      }
    },

    async load(npcId) {
      const sid = useGameStore.getState().session?.sessionId
      if (!sid) return

      const epoch = messageEpoch
      const currentSession = sessionEpoch

      const isCurrent = () =>
        epoch === messageEpoch &&
        currentSession === sessionEpoch &&
        useGameStore.getState().session?.sessionId === sid

      try {
        const history = await api.getMessages(sid, npcId)

        // 이전 게임의 GET 응답이 새 게임의 대화를 덮지 않도록 합니다.
        if (isCurrent() && !inFlight) {
          set({
            messages: {
              ...get().messages,
              [npcId]: history,
            },
          })
        }
      } catch {
        // 기록 조회 실패만으로 새 대화를 차단하지 않습니다.
      } finally {
        if (isCurrent()) {
          set({
            loaded: {
              ...get().loaded,
              [npcId]: true,
            },
          })
        }
      }
    },

    send: (npcId, text) =>
      run(
        npcId,
        text,
        (sid) => api.sendMessage(sid, npcId, text),
      ),

    present: (npcId, evidenceId, title) =>
      run(
        npcId,
        `[증거 제시] ${title}`,
        (sid) => api.presentEvidence(sid, npcId, evidenceId),
      ),
  }
})
