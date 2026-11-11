import type { AccuseResponse } from '../api/types'
import type { SceneLine } from './endingScenes'

/** 엔딩 도감. 달성한 엔딩은 이 기기에 남고, "새로 시작"을 해도 지워지지 않는다. 잠긴 엔딩의 이름·조건은 보여주지 않는다. */
export type EndingKey = 'FULL' | 'ESTIMATED' | 'NO_EVIDENCE' | 'UNSOLVED' | 'DEEP'

export const ENDINGS: { key: EndingKey; label: string; summary: string }[] = [
  { key: 'FULL', label: '사건 해결', summary: '범인을 밝혀내고 신기범 사건을 해결했다.' },
  { key: 'ESTIMATED', label: '추정 성립', summary: '범인의 이름은 맞혔지만 입증은 더 필요한 채 수사가 끝났다.' },
  { key: 'NO_EVIDENCE', label: '증거 부족', summary: '붙잡을 증거가 모자라 누구도 특정하지 못한 채 수사가 끝났다.' },
  { key: 'UNSOLVED', label: '수사 실패', summary: '지목은 빗나갔고, 진실은 어둠 속에 남았다.' },
  { key: 'DEEP', label: '심화 엔딩', summary: '사건 너머의 오래된 진실까지 밝혀냈다.' },
]

const KEY = 'serin-endings-seen'

export function endingKeyOf(r: AccuseResponse): EndingKey {
  if (r.endingKind === 'DEEP') return 'DEEP'
  if (r.result === 'FULL') return 'FULL'
  if (r.result === 'ESTIMATED') return 'ESTIMATED'
  if (r.result === 'NOT_ENOUGH_EVIDENCE') return 'NO_EVIDENCE'
  return 'UNSOLVED'
}

export function loadSeenEndings(): EndingKey[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '[]') as string[]
    return ENDINGS.map((e) => e.key).filter((k) => v.includes(k))
  } catch { return [] }
}

export function recordEnding(k: EndingKey): void {
  try {
    const cur = loadSeenEndings()
    if (!cur.includes(k)) localStorage.setItem(KEY, JSON.stringify([...cur, k]))
  } catch { /* ignore */ }
}

/** 본 엔딩의 대사 장면을 기기에 남겨 첫 화면·최종 화면에서 다시 볼 수 있게 한다. */
const SCENE_STORE = 'serin-ending-scenes'
export function saveEndingScene(k: EndingKey, scene: SceneLine[]): void {
  try {
    const all = JSON.parse(localStorage.getItem(SCENE_STORE) ?? '{}') as Record<string, SceneLine[]>
    all[k] = scene
    localStorage.setItem(SCENE_STORE, JSON.stringify(all))
  } catch { /* ignore */ }
}
export function loadEndingScene(k: EndingKey): SceneLine[] | null {
  try {
    const all = JSON.parse(localStorage.getItem(SCENE_STORE) ?? '{}') as Record<string, SceneLine[]>
    return all[k]?.length ? all[k] : null
  } catch { return null }
}
