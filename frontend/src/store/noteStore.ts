import { create } from 'zustand'

// 추리 노트: 플레이어가 직접 쓰는 개인 기록. 로컬에만 저장하고 서버로 보내지 않는다.
export const NOTE_SECTIONS = [
  { key: 'people', title: '인물 관계 및 특징', hint: '인물에 대해 관찰한 것을 적어 보세요.' },
  { key: 'statements', title: '인물별 진술', hint: '누가 무슨 말을 했는지, 어디가 모순인지.' },
  { key: 'timeline', title: '시간대별 사건 정리', hint: '사건 전후의 시간 순서를 정리해 보세요.' },
  { key: 'evidence', title: '증거와 의문점', hint: '증거를 어떻게 해석하는지, 남은 의문은 무엇인지.' },
  { key: 'theory', title: '나만의 추리', hint: '사건의 진실이 무엇이라고 생각하는지 자유롭게.' },
] as const

export type NoteKey = (typeof NOTE_SECTIONS)[number]['key']
export type NoteData = Record<NoteKey, string>

const KEY = 'serin-notes-v1'
const empty = (): NoteData => ({ people: '', statements: '', timeline: '', evidence: '', theory: '' })

function load(): NoteData {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...empty(), ...(JSON.parse(raw) as Partial<NoteData>) }
  } catch { /* 저장소를 못 쓰면 메모리만 사용 */ }
  return empty()
}

interface NoteStore {
  notes: NoteData
  panelOpen: boolean
  setNote: (key: NoteKey, text: string) => void
  setPanel: (open: boolean) => void
  /** 새 게임 시작 시 노트를 비운다 */
  clear: () => void
}

export const useNoteStore = create<NoteStore>((set, get) => ({
  notes: load(),
  panelOpen: false,
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
