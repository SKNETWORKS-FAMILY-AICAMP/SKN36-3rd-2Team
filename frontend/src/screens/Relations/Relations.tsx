
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock, MessageCircle } from 'lucide-react'

import { api } from '../../api/client'
import type { RelationGraph } from '../../api/types'

import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import CharacterPortrait from '../../components/CharacterPortrait'

import {
  BOARD_POS,
  NPC_PUBLIC,
  npcName,
  type CharacterId,
} from '../../data/characters'

import { useGameStore } from '../../store/gameStore'
import styles from './Relations.module.css'

// 피해자 정보
const VICTIM_ID = 'V01' as const

const VICTIM = {
  id: VICTIM_ID,
  name: '신기범',
  title: '사건 피해자',
  age: '',
  look: '',
}

// 모든 관계도 좌표를 한곳에서 관리합니다.
// characters.ts에 V01이 없어도 정상 작동합니다.
const BOARD_COORDS: Record<
  string,
  { x: number; y: number; tilt: number }
> = {
  ...BOARD_POS,
  V01: {
    x: 50,
    y: 54,
    tilt: 0,
  },
}

const EMPTY_GRAPH: RelationGraph = {
  nodes: [],
  edges: [],
}

type SelectedId = CharacterId | typeof VICTIM_ID

const hasBoardPosition = (id: string): boolean =>
  Object.prototype.hasOwnProperty.call(BOARD_COORDS, id)

export default function Relations() {
  const navigate = useNavigate()

  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)

  const [graph, setGraph] = useState<RelationGraph | null>(null)
  const [sel, setSel] = useState<SelectedId | null>(null)

  const [hoverEdge, setHoverEdge] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sid = session?.sessionId

  const stamp = [
    session?.unlockedNpcs.join(',') ?? '',
    session?.foundEvidence.join(',') ?? '',
    session?.phase ?? '',
  ].join('|')

  // 기존 세션 복구
  useEffect(() => {
    void ensure().catch((err: unknown) => {
      setError(
        err instanceof Error
          ? err.message
          : '게임 세션을 불러오지 못했습니다.',
      )
    })
  }, [ensure])

  // 관계도 데이터 조회
  useEffect(() => {
    if (!sid) {
      setGraph(null)
      return
    }

    let active = true

    setLoading(true)
    setError(null)
    setGraph(null)

    void api
      .getRelations(sid)
      .then((data) => {
        if (!active) return

        setGraph(data)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!active) return

        setGraph(EMPTY_GRAPH)
        setError(
          err instanceof Error
            ? err.message
            : '인물 관계도를 불러오지 못했습니다.',
        )
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    // 이전 세션의 응답이 새 화면을 덮어쓰지 않도록 방지
    return () => {
      active = false
    }
  }, [sid, stamp])

  // 서버에서 공개된 노드인지 확인
  const isOpen = (id: string): boolean =>
    graph?.nodes.some(
      (node) => node.id === id && node.unlocked,
    ) ?? false

  // 선택된 인물 정보
  const picked = useMemo(() => {
    if (!sel) return undefined

    if (sel === VICTIM_ID) {
      return VICTIM
    }

    return NPC_PUBLIC.find((npc) => npc.id === sel)
  }, [sel])

  // 양 끝 좌표가 유효하고 공개된 관계선만 렌더링
  const edges = useMemo(() => {
    if (!graph) return []

    const visibleIds = new Set(
      graph.nodes
        .filter((node) => node.unlocked)
        .map((node) => node.id),
    )

    return graph.edges.filter(
      (edge) =>
        visibleIds.has(edge.source) &&
        visibleIds.has(edge.target) &&
        hasBoardPosition(edge.source) &&
        hasBoardPosition(edge.target),
    )
  }, [graph])

  // 좌표가 없는 노드에 접근하지 않도록 기본값 처리
  const center = (id: string) =>
    BOARD_COORDS[id] ?? {
      x: 50,
      y: 50,
      tilt: 0,
    }


  return (
    <div className={styles.page}>
      <TopNav />
      <Toasts />

      <main className={styles.main}>
        <section
          className={styles.boardWrap}
          aria-label="인물 관계도"
        >
          <header className={`${styles.head} page-head`}>
            <h1 className="serif">인물 관계도</h1>

            <p>
              조사로 확인된 관계만 붉은 실로 이어집니다.
            </p>

            {loading && (
              <p role="status">
                관계도를 불러오는 중입니다...
              </p>
            )}

            {error && (
              <p role="alert" style={{ color: '#e59686' }}>
                {error}
              </p>
            )}
          </header>

          <div className={styles.board}>
            {/* 관계 연결선 */}
            <svg
              className={styles.strings}
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {edges.map((edge) => {
                const a = center(edge.source)
                const b = center(edge.target)

                const mine =
                  !sel ||
                  edge.source === sel ||
                  edge.target === sel

                return (
                  <line
                    key={edge.id}
                    x1={a.x}
                    y1={a.y + 4}
                    x2={b.x}
                    y2={b.y + 4}
                    className={
                      mine || hoverEdge === edge.id
                        ? styles.hot
                        : styles.dimLine
                    }
                  />
                )
              })}
            </svg>

            {/* 관계 설명 태그 */}
            {edges.map((edge, index) => {
              const a = center(edge.source)
              const b = center(edge.target)

              const mine =
                !sel ||
                edge.source === sel ||
                edge.target === sel

              const crowded = edges.length > 4

              const show =
                !crowded ||
                (sel ? mine : false) ||
                hoverEdge === edge.id

              const t =
                0.42 + ((index * 3) % 5) * 0.04

              const x =
                a.x + (b.x - a.x) * t

              const y =
                a.y + (b.y - a.y) * t + 4

              return (
                <button
                  key={edge.id}
                  type="button"
                  className={[
                    styles.tag,
                    show ? '' : styles.dot,
                    mine ? '' : styles.dimTag,
                  ].join(' ')}
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                  }}
                  onMouseEnter={() =>
                    setHoverEdge(edge.id)
                  }
                  onMouseLeave={() =>
                    setHoverEdge(null)
                  }
                  onFocus={() =>
                    setHoverEdge(edge.id)
                  }
                  onBlur={() =>
                    setHoverEdge(null)
                  }
                  aria-label={
                    `${npcName(edge.source)}와 ` +
                    `${npcName(edge.target)}: ${edge.label}`
                  }
                >
                  {show ? edge.label : ''}
                </button>
              )
            })}

            {/* 피해자 신기범 */}
            {isOpen(VICTIM_ID) && (
              <button
                key={VICTIM_ID}
                type="button"
                className={[
                  styles.pin,
                  sel === VICTIM_ID ? styles.sel : '',
                ].join(' ')}
                style={{
                  left: `${BOARD_COORDS.V01.x}%`,
                  top: `${BOARD_COORDS.V01.y}%`,
                  ['--tilt' as string]: '0deg',
                }}
                onClick={() => setSel(VICTIM_ID)}
                aria-label="신기범"
              >
                <i
                  className={styles.nail}
                  aria-hidden="true"
                />

                <span className={styles.photo}>
                  <CharacterPortrait
                    id={VICTIM_ID}
                    alt="신기범"
                  />
                </span>

                <span className={styles.name}>
                  신기범
                </span>
              </button>
            )}

            {/* NPC 10명 */}
            {NPC_PUBLIC.map((npc) => {
              const pos = center(npc.id)
              const unlocked = isOpen(npc.id)

              return (
                <button
                  key={npc.id}
                  type="button"
                  disabled={!unlocked}
                  className={[
                    styles.pin,
                    unlocked ? '' : styles.locked,
                    sel === npc.id ? styles.sel : '',
                  ].join(' ')}
                  style={{
                    left: `${pos.x}%`,
                    top: `${pos.y}%`,
                    ['--tilt' as string]:
                      `${pos.tilt}deg`,
                  }}
                  onClick={() => setSel(npc.id)}
                  aria-label={
                    unlocked
                      ? npc.name
                      : '아직 알 수 없는 인물'
                  }
                >
                  <i
                    className={styles.nail}
                    aria-hidden="true"
                  />

                  <span className={styles.photo}>
                    {unlocked ? (
                      <CharacterPortrait
                        id={npc.id}
                        alt=""
                      />
                    ) : (
                      <Lock size={22} />
                    )}
                  </span>

                  <span className={styles.name}>
                    {unlocked ? npc.name : '???'}
                  </span>
                </button>
              )
            })}
          </div>
        </section>

        {/* 관계도 디버그 */}


        {/* 선택 인물 상세 */}
        <aside
          className={styles.side}
          aria-label="인물 정보"
        >
          {!picked ? (
            <p className={styles.empty}>
              인물을 선택하면 간단한 프로필이
              표시됩니다.
            </p>
          ) : (
            <div className={styles.card}>
              <CharacterPortrait
                id={picked.id}
                alt={`${picked.name}의 사진`}
                className={styles.big}
              />

              <h2 className="serif">
                {picked.name}
              </h2>

              <p className={styles.role}>
                {picked.title}
              </p>

              <dl>
                {picked.age && (
                  <div>
                    <dt>나이대</dt>
                    <dd>{picked.age}</dd>
                  </div>
                )}

                {picked.look && (
                  <div>
                    <dt>외형</dt>
                    <dd>{picked.look}</dd>
                  </div>
                )}
              </dl>

              <h3>확인된 관계</h3>

              <ul className={styles.list}>
                {edges
                  .filter(
                    (edge) =>
                      edge.source === picked.id ||
                      edge.target === picked.id,
                  )
                  .map((edge) => (
                    <li key={edge.id}>
                      {npcName(
                        edge.source === picked.id
                          ? edge.target
                          : edge.source,
                      )}
                      {' · '}
                      {edge.label}
                    </li>
                  ))}

                {edges.every(
                  (edge) =>
                    edge.source !== picked.id &&
                    edge.target !== picked.id,
                ) && (
                  <li className={styles.none}>
                    아직 확인된 관계가 없습니다.
                  </li>
                )}
              </ul>

              {/* 피해자는 대화할 수 없습니다.
                  게임 종료 이후에도 대화를 차단합니다. */}
              {picked.id !== VICTIM_ID &&
                session?.phase === 'INVESTIGATION' && (
                  <button
                    type="button"
                    className={styles.talk}
                    onClick={() =>
                      navigate(`/chat/${picked.id}`)
                    }
                  >
                    <MessageCircle size={16} />
                    {picked.name}와 대화하기
                  </button>
                )}
            </div>
          )}
        </aside>
      </main>
    </div>
  )
}
