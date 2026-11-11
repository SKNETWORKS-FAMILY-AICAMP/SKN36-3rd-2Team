import { create } from 'zustand'

// 추리 노트: 플레이어가 직접 쓰는 개인 기록. 로컬에만 저장하고 서버로 보내지 않는다.
export const NOTE_SECTIONS = [
  { key: 'theory', title: '나만의 추리', hint: '사건의 진실이 무엇이라고 생각하는지 자유롭게.' },
] as const

export type NoteKey = (typeof NOTE_SECTIONS)[number]['key']
export type NoteData = Record<NoteKey, string>

const KEY = 'serin-notes-v1'
const empty = (): NoteData => ({ theory: '' })

function load(): NoteData {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const old = JSON.parse(raw)
      const sections = [['people', '인물 관계 및 특징'], ['statements', '인물별 진술'], ['timeline', '시간대별 사건 정리'], ['evidence', '증거와 의문점']]
      const entries = sections.filter(([key]) => typeof old[key] === 'string' && old[key].trim())
      return { theory: [old.theory, ...entries.map(([key, title]) => title + '\n' + old[key])].filter(Boolean).join('\n\n') }
    }
  } catch { /* 저장소를 못 쓰면 메모리만 사용 */ }
  return empty()
}

const WIDTH_KEY = 'serin-notes-width'
export const NOTE_MIN_W = 320
export const NOTE_DEFAULT_W = 560
export const clampWidth = (w: number) => {
  const vw = window.innerWidth
  const max = vw <= 700 ? vw : Math.max(NOTE_MIN_W, vw - 80) // 좁은 화면은 화면 전체까지 허용
  return Math.round(Math.max(Math.min(NOTE_MIN_W, vw), Math.min(w, max)))
}
function loadWidth(): number {
  try { const v = Number(localStorage.getItem(WIDTH_KEY)); if (v > 0) return clampWidth(v) } catch { /* ignore */ }
  return NOTE_DEFAULT_W
}

interface NoteStore {
  notes: NoteData
  panelOpen: boolean
  /** 노트 패널 폭(px). 왼쪽 가장자리를 끌어 조절한다 */
  panelWidth: number
  setPanelWidth: (w: number) => void
  setNote: (key: NoteKey, text: string) => void
  setPanel: (open: boolean) => void
  /** 새 게임 시작 시 노트를 비운다 */
  clear: () => void
}

export const useNoteStore = create<NoteStore>((set, get) => ({
  notes: load(),
  panelOpen: false,
  panelWidth: loadWidth(),
  setPanelWidth(w) {
    const panelWidth = clampWidth(w)
    set({ panelWidth })
    try { localStorage.setItem(WIDTH_KEY, String(panelWidth)) } catch { /* ignore */ }
  },
  setNote(key, text) {
    const notes = { ...get().notes, [key]: text }
    set({ notes })
    try { localStorage.setItem(KEY, JSON.stringify(notes)) } catch { /* ignore */ }
  },
  setPanel: (panelOpen) => set({ panelOpen }),
  clear() {
    set({ notes: empty(), panelOpen: false })
    try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  },
}))
