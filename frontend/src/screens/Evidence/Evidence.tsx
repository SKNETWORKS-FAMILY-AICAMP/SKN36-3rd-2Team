import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Lock } from 'lucide-react'
import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import { evidencePhoto } from '../../data/evidenceImages'
import CharacterPortrait from '../../components/CharacterPortrait'
import { evidenceSlots } from '../../data/publicData'
import { npcName } from '../../data/characters'
import { SHOW_COLLECTION_PERCENT } from '../../config'
import { useGameStore } from '../../store/gameStore'
import type { EvidenceDetail } from '../../api/types'
import styles from './Evidence.module.css'

const ROUTE_LABEL: Record<NonNullable<EvidenceDetail['acquiredBy']>, string> = {
  question: '질문으로 확보',
  present: '증거 제시로 확보',
  initial: '현장에서 확보',
}
const routeLabel = (d: EvidenceDetail) => (d.acquiredBy ? ROUTE_LABEL[d.acquiredBy] : '서버 기록 미제공')

/** 획득 경로·보유 인물 요약 칩 (상세·비교 공용) */
function EvidenceChips({ detail }: { detail: EvidenceDetail }) {
  return (
    <p className={styles.chips} aria-label="증거 요약">
      <span>{routeLabel(detail)}</span>
      <span>보유 · {npcName(detail.holderId)}</span>
    </p>
  )
}

/** 목록 칸 썸네일. 사진을 못 불러오면(서버에 사진 없음 등) 문서 아이콘으로 바꾼다 */
function EvidenceThumb({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <FileText size={28} />
  return <img className={styles.thumb} src={src} alt="" loading="lazy" draggable={false} onError={() => setFailed(true)} />
}

/** 증거 사진 (상세·비교 공용). 이미지가 없거나 못 불러오면 숨긴다 */
function EvidencePhotoFigure({ sessionId, id }: { sessionId?: string; id: string }) {
  const ph = evidencePhoto(sessionId, id)
  if (!ph) return null
  return (
    <figure className={styles.prop}>
      <img src={ph.src} alt="" draggable={false} onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = 'none' }} />
      <figcaption>{ph.caption}</figcaption>
    </figure>
  )
}

export default function Evidence() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const cache = useGameStore((s) => s.evidence)
  const loadEvidence = useGameStore((s) => s.loadEvidence)
  const [selected, setSelected] = useState<string | null>(null)
  const [docIdx, setDocIdx] = useState(0)
  // 증거 비교: 켜면 증거를 최대 2개까지 골라 나란히 본다. 3번째를 고르면 먼저 고른 것이 빠진다.
  const [compareMode, setCompareMode] = useState(false)
  const [picks, setPicks] = useState<string[]>([])
  // 처음 들어올 때의 '새 증거' 목록을 기억해 NEW 표시를 하고, 내비게이션 점은 지운다

  useEffect(() => { void ensure() }, [ensure])

  const found = session?.foundEvidence ?? []
  const slots = evidenceSlots(session?.evidenceTotal)
  const foundKey = found.join(',')
  useEffect(() => {
    found.forEach((id) => void loadEvidence(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foundKey, session?.sessionId])

  const detail = selected ? cache[selected] : undefined
  const canCompare = found.length >= 2

  const toggleCompare = () => {
    setCompareMode((on) => !on)
    // 비교를 시작할 때 이미 보고 있던 증거를 첫 번째로 넣어 준다
    setPicks(!compareMode && selected ? [selected] : [])
  }

  const pickItem = (id: string) => {
    if (!compareMode) { setSelected(id); setDocIdx(0); return }
    setPicks((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-2)))
  }
  const coll = session?.collection
  const pct = coll && coll.total > 0 ? Math.round((coll.score / coll.total) * 100) : 0

  return (
    <div className={styles.page}>
      <TopNav />
      <Toasts />
      <main className={styles.main}>
        <section className={styles.desk} aria-label="증거 목록">
          <header className={`${styles.head} page-head`}>
            <div>
              <h1 className="serif">증거 보관함</h1>
              <p>수사 중 확보한 자료가 책상 위에 놓입니다.</p>
            </div>
            {SHOW_COLLECTION_PERCENT && coll && coll.total > 0 ? (
              <div className={styles.meter} aria-label={`수집률 ${pct}퍼센트`}>
                <span className={styles.pct}>{pct}<small>%</small></span>
                <span className={styles.bar}><i style={{ width: `${pct}%` }} /></span>
                <span className={styles.lbl}>수집률 · 확보 {found.length} / {slots.length}</span>
              </div>
            ) : (
              <div className={styles.meter} aria-label={`확보 ${found.length}개`}>
                <span className={styles.pct}>{found.length}<small> / {slots.length}</small></span>
                <span className={styles.bar}><i style={{ width: `${(found.length / slots.length) * 100}%` }} /></span>
                <span className={styles.lbl}>확보한 증거</span>
              </div>
            )}
            <div className={styles.compareBar}>
              <button
                type="button"
                className={`btn ${compareMode ? 'btn--primary' : ''}`}
                onClick={toggleCompare}
                disabled={!canCompare && !compareMode}
                aria-pressed={compareMode}
                title={canCompare ? undefined : '증거를 2개 이상 확보하면 비교할 수 있습니다.'}
              >
                {compareMode ? '비교 끝내기' : '증거 비교'}
              </button>
              {compareMode && (
                <span className={styles.compareHint} aria-live="polite">비교할 증거를 2개까지 고르세요 · {picks.length} / 2</span>
              )}
            </div>
          </header>

          <ul className={styles.grid}>
            {slots.map((id, i) => {
              const has = found.includes(id)
              const d = cache[id]
              return (
                <li key={id} style={{ ['--tilt' as string]: `${((i * 37) % 7) - 3}deg` }}>
                  <button
                    type="button"
                    disabled={!has}
                    className={`${styles.item} ${has ? styles.have : styles.lost} ${(compareMode ? picks.includes(id) : selected === id) ? styles.sel : ''}`}
                    onClick={() => pickItem(id)}
                    aria-pressed={compareMode ? picks.includes(id) : undefined}
                    aria-label={has ? (d?.title ?? id) : '아직 확보하지 못한 증거'}
                  >
                    <span className={styles.no}>{id}</span>
                    {compareMode && picks.includes(id) && <i className={styles.pickNo}>{picks.indexOf(id) + 1}</i>}
                    {has && d && evidencePhoto(session?.sessionId, id) ? (
                      <EvidenceThumb key={id} src={evidencePhoto(session?.sessionId, id)!.thumb} />
                    ) : has ? <FileText size={28} /> : <Lock size={24} />}
                    <span className={styles.name}>{has ? (d?.title ?? '불러오는 중…') : '잠김 · 인물과 대화해 단서 찾기'}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <aside className={styles.viewer} aria-label={compareMode ? '증거 비교' : '증거 상세'}>
          {compareMode ? (
            picks.length === 0 ? (
              <p className={styles.empty}>왼쪽에서 비교할 증거를 2개까지 고르세요.</p>
            ) : (
              <div className={styles.compare}>
                {picks.map((id) => {
                  const d = cache[id]
                  return d ? (
                    <article key={id} className={`${styles.paper} ${styles.paperCompact}`}>
                      <span className={styles.stamp}>{d.id}</span>
                      <h2 className="serif">{d.title}</h2>
                      <EvidenceChips detail={d} />
                      <EvidencePhotoFigure sessionId={session?.sessionId} id={d.id} />
                      {(d.documents ?? []).length > 1 ? (
                        d.documents!.map((doc) => (
                          <section key={doc.id} className={styles.docBlock}>
                            <h3>{doc.label} · {doc.title}</h3>
                            <p className={styles.body}>{doc.body}</p>
                          </section>
                        ))
                      ) : (
                        <p className={styles.body}>{d.documents?.[0]?.body ?? d.body ?? '증거 원문은 아직 서버에서 제공되지 않았습니다.'}</p>
                      )}
                    </article>
                  ) : (
                    <p key={id} className={styles.empty}>불러오는 중…</p>
                  )
                })}
              </div>
            )
          ) : !detail ? (
            <div className={styles.cover}>
              <span className={styles.coverTab}>CASE 001</span>
              <h2 className="serif">사건 기록철</h2>
              <p className={styles.coverSub}>세린국제학교 구 본관 · 신기범 사건</p>
              <span className={styles.coverSeal}>조사 중</span>
              <p className={styles.coverHint}>
                {found.length === 0
                  ? '아직 확보한 증거가 없습니다. 인물들에게 질문하며 단서를 찾아보세요.'
                  : '왼쪽에서 증거를 선택하면 문서를 펼쳐 볼 수 있습니다.'}
              </p>
            </div>
          ) : (
            <article className={styles.paper}>
              <span className={styles.stamp}>{detail.id}</span>
              {(() => {
                const docs = detail.documents ?? []
                const multi = docs.length > 1
                const cur = multi ? docs[Math.min(docIdx, docs.length - 1)] : null
                return (
                  <>
                    {multi && (
                      <div className={styles.docTabs} role="tablist" aria-label="문서 선택">
                        {docs.map((d, i) => (
                          <button
                            key={d.id}
                            type="button"
                            role="tab"
                            aria-selected={i === docIdx}
                            className={`${styles.docTab} ${i === docIdx ? styles.docTabOn : ''}`}
                            onClick={() => setDocIdx(i)}
                          >
                            {d.label}
                          </button>
                        ))}
                      </div>
                    )}
                    <h2 className="serif">{cur ? cur.title : detail.title}</h2>
                    <EvidenceChips detail={detail} />
                    <EvidencePhotoFigure key={detail.id} sessionId={session?.sessionId} id={detail.id} />
                    <p className={styles.body}>{(cur ? cur.body : detail.body) ?? "증거 원문은 아직 서버에서 제공되지 않았습니다."}</p>
                  </>
                )
              })()}
              <dl>
                <div>
                  <dt>보유 인물</dt>
                  <dd>
                    <button type="button" className={styles.who} onClick={() => navigate(`/chat/${detail.holderId}`)}>
                      <CharacterPortrait id={detail.holderId} alt="" className={styles.mini} />
                      {npcName(detail.holderId)}
                    </button>
                  </dd>
                </div>
                <div><dt>획득 경로</dt><dd>{routeLabel(detail)}</dd></div>
                <div>
                  <dt>확인된 관계</dt>
                  <dd>
                    {detail.confirmedRelations.length === 0 ? '아직 확인된 관계가 없습니다.' : (
                      <ul className={styles.rel}>
                        {detail.confirmedRelations.map((r) => (
                          <li key={r.id + r.label}>{npcName(r.id)} · {r.label}</li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
              </dl>
            </article>
          )}
        </aside>
      </main>
    </div>
  )
}
