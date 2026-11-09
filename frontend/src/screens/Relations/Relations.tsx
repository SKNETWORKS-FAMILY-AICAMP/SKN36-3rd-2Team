import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { mockDebug } from '../../api/mockApi'
import { useNavigate } from 'react-router-dom'
import { Lock, MessageCircle } from 'lucide-react'
import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import CharacterPortrait from '../../components/CharacterPortrait'
import { BOARD_POS, NPC_PUBLIC, npcName, type CharacterId } from '../../data/characters'
import { api } from '../../api/client'
import type { RelationGraph } from '../../api/types'
import { useGameStore } from '../../store/gameStore'
import styles from './Relations.module.css'

export default function Relations() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const [graph, setGraph] = useState<RelationGraph | null>(null)
  const [sel, setSel] = useState<CharacterId | null>(null)
  const [params] = useSearchParams()
  const [hoverEdge, setHoverEdge] = useState<string | null>(null)

  useEffect(() => { void ensure() }, [ensure])

  const sid = session?.sessionId
  const stamp = `${session?.unlockedNpcs.join()}|${session?.foundEvidence.join()}`
  useEffect(() => {
    if (sid) void api.getRelations(sid).then(setGraph).catch(() => setGraph({ nodes: [], edges: [] }))
  }, [sid, stamp])

  const open = (id: string) => graph?.nodes.find((n) => n.id === id)?.unlocked ?? false
  const picked = sel ? NPC_PUBLIC.find((n) => n.id === sel) : undefined
  // 양쪽 인물이 모두 해금된 관계선만 그린다
  const edges = (graph?.edges ?? []).filter((e) => open(e.source) && open(e.target))
  const center = (id: string) => BOARD_POS[id as CharacterId]

  return (
    <div className={styles.page}>
      <TopNav />
      <Toasts />
      <main className={styles.main}>
        <section className={styles.boardWrap} aria-label="인물 관계도">
          <header className={`${styles.head} page-head`}>
            <h1 className="serif">인물 관계도</h1>
            <p>조사로 확인된 관계만 붉은 실로 이어집니다.</p>
          </header>
          <div className={styles.board}>
            <svg className={styles.strings} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {edges.map((e) => {
                const a = center(e.source), b = center(e.target)
                const mine = !sel || e.source === sel || e.target === sel
                return (
                  <line
                    key={e.id}
                    x1={a.x} y1={a.y + 4} x2={b.x} y2={b.y + 4}
                    className={mine || hoverEdge === e.id ? styles.hot : styles.dimLine}
                  />
                )
              })}
            </svg>
            {edges.map((e, i) => {
              const a = center(e.source), b = center(e.target)
              const mine = !sel || e.source === sel || e.target === sel
              // 관계가 많으면 선택/호버한 관계의 설명만 펼치고 나머지는 점으로 줄인다
              const crowded = edges.length > 4
              const show = !crowded || (sel ? mine : false) || hoverEdge === e.id
              // 같은 위치에 겹치지 않도록 선 위의 위치를 조금씩 비껴 놓는다
              const t = 0.42 + ((i * 3) % 5) * 0.04
              return (
                <button
                  key={e.id}
                  type="button"
                  className={`${styles.tag} ${show ? '' : styles.dot} ${mine ? '' : styles.dimTag}`}
                  style={{ left: `${a.x + (b.x - a.x) * t}%`, top: `${a.y + (b.y - a.y) * t + 4}%` }}
                  onMouseEnter={() => setHoverEdge(e.id)}
                  onMouseLeave={() => setHoverEdge(null)}
                  onFocus={() => setHoverEdge(e.id)}
                  onBlur={() => setHoverEdge(null)}
                  aria-label={`${npcName(e.source)}와 ${npcName(e.target)}: ${e.label}`}
                >
                  {show ? e.label : ''}
                </button>
              )
            })}
            {NPC_PUBLIC.map((n) => {
              const pos = BOARD_POS[n.id]
              const unlocked = open(n.id)
              return (
                <button
                  key={n.id}
                  type="button"
                  disabled={!unlocked}
                  className={`${styles.pin} ${unlocked ? '' : styles.locked} ${sel === n.id ? styles.sel : ''}`}
                  style={{ left: `${pos.x}%`, top: `${pos.y}%`, ['--tilt' as string]: `${pos.tilt}deg` }}
                  onClick={() => setSel(n.id)}
                  aria-label={unlocked ? n.name : '아직 알 수 없는 인물'}
                >
                  <i className={styles.nail} aria-hidden="true" />
                  <span className={styles.photo}>
                    {unlocked ? <CharacterPortrait id={n.id} alt="" /> : <Lock size={22} />}
                  </span>
                  <span className={styles.name}>{unlocked ? n.name : '???'}</span>
                </button>
              )
            })}
          </div>
        </section>

        {params.has('debug') && (
          <button
            type="button"
            style={{ position: 'fixed', left: 12, bottom: 12, zIndex: 60, font: '12px monospace', color: '#4a8f8a', background: '#000c', border: '1px dashed #4a8f8a' }}
            onClick={() => { mockDebug.stressEdges(); if (sid) void api.getRelations(sid).then(setGraph) }}
          >
            DEBUG 관계선 많이
          </button>
        )}
        <aside className={styles.side} aria-label="인물 정보">
          {!picked ? (
            <p className={styles.empty}>인물을 선택하면 간단한 프로필이 표시됩니다.</p>
          ) : (
            <div className={styles.card}>
              <CharacterPortrait id={picked.id} alt={`${picked.name}의 사진`} className={styles.big} />
              <h2 className="serif">{picked.name}</h2>
              <p className={styles.role}>{picked.title}</p>
              <dl>
                <div><dt>나이대</dt><dd>{picked.age}</dd></div>
                <div><dt>외형</dt><dd>{picked.look}</dd></div>
              </dl>
              <h3>확인된 관계</h3>
              <ul className={styles.list}>
                {edges.filter((e) => e.source === picked.id || e.target === picked.id).map((e) => (
                  <li key={e.id}>
                    {npcName(e.source === picked.id ? e.target : e.source)} · {e.label}
                  </li>
                ))}
                {edges.every((e) => e.source !== picked.id && e.target !== picked.id) && (
                  <li className={styles.none}>아직 확인된 관계가 없습니다.</li>
                )}
              </ul>
              <button type="button" className={styles.talk} onClick={() => navigate(`/chat/${picked.id}`)}>
                <MessageCircle size={16} /> {picked.name}와 대화하기
              </button>
            </div>
          )}
        </aside>
      </main>
    </div>
  )
}
