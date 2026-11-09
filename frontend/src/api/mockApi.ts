import type { GameApi } from './client'
import type { AccuseResponse, ChatReply, GameEvent, Message, RelationGraph, SessionState } from './types'
import { CASE_INTRO } from '../mock/publicData'
import { classify, DEMO_EDGES, DEMO_EVIDENCE, DEMO_FILLER, DEMO_RULES, NPC_LINES } from '../mock/chatData'

// mock 서버 계층: 백엔드 없이 화면을 시연하기 위한 임시 구현.
// 실제 판정/해금 로직이 아니라 시연용 규칙이다. 상태는 localStorage에 보관한다.

const KEY = 'serin-mock-v1'
const ALL_NPCS = ['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10']
const TOTAL = 21

interface Store {
  state: SessionState
  messages: Record<string, Message[]>
  fired: string[]
}

function fresh(): Store {
  return {
    state: {
      sessionId: `mock-${Date.now().toString(36)}`,
      unlockedNpcs: ['C01'],
      foundEvidence: [],
      collection: { score: 0, total: TOTAL },
      attemptsLeft: 3,
      canAccuse: false,
    },
    messages: {},
    fired: [],
  }
}

function load(): Store {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw) as Store
  } catch { /* 저장소를 못 쓰면 메모리만 사용 */ }
  return fresh()
}

let db: Store = load()
let stress = false // 개발용: 관계선이 많을 때의 화면 확인

function save() {
  db.state.canAccuse = db.state.collection.score >= 3 && db.state.attemptsLeft > 0 // 시연용 기준
  try { localStorage.setItem(KEY, JSON.stringify(db)) } catch { /* ignore */ }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
let seq = 0
const mid = () => `m${Date.now().toString(36)}${(seq++).toString(36)}`

function push(npcId: string, role: Message['role'], text: string) {
  const list = (db.messages[npcId] ??= [])
  list.push({ id: mid(), role, text, at: Date.now() })
}

function applyRule(npcId: string, text: string): GameEvent[] {
  const cat = classify(text)
  const rule = DEMO_RULES.find((r) => r.npc === npcId && r.cat === cat)
  const key = `${npcId}:${cat}`
  if (!rule || db.fired.includes(key)) return []
  db.fired.push(key)
  const events: GameEvent[] = []
  if (rule.evidence && !db.state.foundEvidence.includes(rule.evidence)) {
    db.state.foundEvidence.push(rule.evidence)
    db.state.collection.score += DEMO_EVIDENCE[rule.evidence]?.score ?? 0
    events.push({ type: 'evidence_found', id: rule.evidence })
  }
  for (const id of rule.unlock ?? []) {
    if (!db.state.unlockedNpcs.includes(id)) {
      db.state.unlockedNpcs.push(id)
      events.push({ type: 'npc_unlocked', id })
    }
  }
  return events
}

function assertUnlocked(npcId: string) {
  if (!db.state.unlockedNpcs.includes(npcId)) throw new Error('아직 만날 수 없는 인물입니다.')
}

export const mockApi: GameApi = {
  async createSession() {
    db = fresh()
    save()
    return { state: structuredClone(db.state), notes: CASE_INTRO.notes }
  },
  async getState() {
    return structuredClone(db.state)
  },
  async getMessages(_sid, npcId) {
    return [...(db.messages[npcId] ?? [])]
  },
  async sendMessage(_sid, npcId, text): Promise<ChatReply> {
    assertUnlocked(npcId)
    push(npcId, 'player', text)
    await sleep(700 + Math.random() * 700)
    const lines = NPC_LINES[npcId]
    const reply = lines ? lines[classify(text)] : '…'
    push(npcId, 'npc', reply)
    const events = applyRule(npcId, text)
    save()
    return { reply, events }
  },
  async presentEvidence(_sid, npcId, evidenceId): Promise<ChatReply> {
    assertUnlocked(npcId)
    if (!db.state.foundEvidence.includes(evidenceId)) throw new Error('보유하지 않은 증거입니다.')
    const ev = DEMO_EVIDENCE[evidenceId]
    push(npcId, 'player', `[증거 제시] ${ev?.title ?? evidenceId}`)
    await sleep(800 + Math.random() * 600)
    const reply = NPC_LINES[npcId]?.present ?? '…'
    push(npcId, 'npc', reply)
    save()
    return { reply, events: [] }
  },
  async getEvidence(_sid, evidenceId) {
    if (!db.state.foundEvidence.includes(evidenceId)) throw new Error('아직 확보하지 못한 증거입니다.')
    const ev = DEMO_EVIDENCE[evidenceId] ?? DEMO_FILLER[evidenceId]
    if (!ev) throw new Error('증거를 찾을 수 없습니다.')
    return {
      id: ev.id,
      title: ev.title,
      body: ev.body,
      documents: ev.documents,
      holderId: ev.holderId,
      acquiredBy: 'question',
      confirmedRelations: ev.relations,
    }
  },
  async getAvailableEvidence() {
    // Mock mode collects evidence automatically while chatting.
    return []
  },
  async collectEvidence() {
    throw new Error('시연 모드에서는 대화로 증거를 자동 획득합니다.')
  },
  async getEnding() {
    throw new Error('Mock 모드에서는 저장된 시연 엔딩을 사용합니다.')
  },
  async getRelations(): Promise<RelationGraph> {
    const nodes = ALL_NPCS.map((id) => ({ id, unlocked: db.state.unlockedNpcs.includes(id) }))
    const extra = stress
      ? ALL_NPCS.flatMap((a, i) => [1, 3, 4].map((k) => ({
          id: `S${a}${k}`, source: a, target: ALL_NPCS[(i + k) % 10], label: `시연 관계 ${i + 1}-${k}`, needs: '',
        })))
      : []
    const edges = [...DEMO_EDGES, ...extra].filter((e) => e.needs === '' || db.state.foundEvidence.includes(e.needs))
      .map(({ id, source, target, label }) => ({ id, source, target, label }))
    return { nodes, edges }
  },
  async accuse(_sid, suspectId, evidenceIds): Promise<AccuseResponse> {
    if (!db.state.canAccuse) throw new Error('아직 지목할 수 없습니다.')
    if (!db.state.unlockedNpcs.includes(suspectId)) throw new Error('지목할 수 없는 인물입니다.')
    if (evidenceIds.length < 1 || evidenceIds.length > 3 || !evidenceIds.every((e) => db.state.foundEvidence.includes(e)))
      throw new Error('근거 증거를 1~3개 선택하세요.')
    await sleep(900)
    // 시연용 고정 응답: 판정 로직 없음. 시도 횟수에 따라 순환한다.
    db.state.attemptsLeft -= 1
    const n = 3 - db.state.attemptsLeft
    save()
    // 개발용: localStorage 'serin-mock-force' 로 첫 지목의 결과를 강제한다 (ESTIMATED | FULL | NOT_ENOUGH_EVIDENCE)
    let force: string | null = null
    try { force = localStorage.getItem('serin-mock-force') } catch { /* ignore */ }
    if (force === 'NOT_ENOUGH_EVIDENCE') {
      db.state.attemptsLeft += 1
      save()
      return { result: 'NOT_ENOUGH_EVIDENCE', attemptsLeft: db.state.attemptsLeft }
    }
    if (force === 'DEEP') {
      db.state.attemptsLeft = 0
      save()
      return { result: 'FULL', attemptsLeft: 0, endingKind: 'DEEP', ending: { title: '심화 엔딩', text: '시연용 심화 엔딩 문장입니다. 실제 문장은 서버가 내려줍니다.' } }
    }
    if (force === 'ESTIMATED') {
      return { result: 'ESTIMATED', attemptsLeft: db.state.attemptsLeft, ending: { title: '추정 엔딩', text: '시연용 추정 엔딩 문장입니다. 실제 문장은 서버가 내려줍니다.' } }
    }
    if (n < 3) return { result: 'WRONG', attemptsLeft: db.state.attemptsLeft }
    if (force === 'GAME_OVER') return { result: 'WRONG', attemptsLeft: 0 } // 마지막 기회 실패(엔딩 문장 없음)
    return {
      result: 'FULL',
      attemptsLeft: 0,
      ending: { title: '시연용 엔딩', text: '실제 엔딩 문장은 서버가 내려줍니다. 이 문장은 화면 확인을 위한 자리표시입니다.' },
    }
  },
}

/** 시연/개발용. http 모드에서는 쓰이지 않는다. */
export const mockDebug = {
  stressEdges() { stress = true },
  unlockAll() {
    db.state.unlockedNpcs = [...ALL_NPCS]
    save()
  },
  grantDemoEvidence() {
    for (const id of Object.keys(DEMO_EVIDENCE)) {
      if (!db.state.foundEvidence.includes(id)) {
        db.state.foundEvidence.push(id)
        db.state.collection.score += DEMO_EVIDENCE[id].score
      }
    }
    save()
  },
  grantAllEvidence() {
    for (const id of [...Object.keys(DEMO_EVIDENCE), ...Object.keys(DEMO_FILLER)]) {
      if (!db.state.foundEvidence.includes(id)) {
        db.state.foundEvidence.push(id)
        db.state.collection.score += (DEMO_EVIDENCE[id] ?? DEMO_FILLER[id]).score
      }
    }
    save()
  },
  reset() {
    db = fresh()
    save()
  },
}
