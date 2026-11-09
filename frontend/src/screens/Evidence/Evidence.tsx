import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Lock } from 'lucide-react'
import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import CharacterPortrait from '../../components/CharacterPortrait'
import { EVIDENCE_SLOTS } from '../../mock/publicData'
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

export default function Evidence() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const cache = useGameStore((s) => s.evidence)
  const loadEvidence = useGameStore((s) => s.loadEvidence)
  const [selected, setSelected] = useState<string | null>(null)
  const [docIdx, setDocIdx] = useState(0)

  useEffect(() => { void ensure() }, [ensure])

  const found = session?.foundEvidence ?? []
  const foundKey = found.join(',')
  useEffect(() => {
    found.forEach((id) => void loadEvidence(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foundKey, session?.sessionId])

  const detail = selected ? cache[selected] : undefined
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
                <span className={styles.lbl}>수집률 · 확보 {found.length} / {EVIDENCE_SLOTS.length}</span>
              </div>
            ) : (
              <div className={styles.meter} aria-label={`확보 ${found.length}개`}>
                <span className={styles.pct}>{found.length}<small> / {EVIDENCE_SLOTS.length}</small></span>
                <span className={styles.bar}><i style={{ width: `${(found.length / EVIDENCE_SLOTS.length) * 100}%` }} /></span>
                <span className={styles.lbl}>확보한 증거</span>
              </div>
            )}
          </header>

          <ul className={styles.grid}>
            {EVIDENCE_SLOTS.map((id, i) => {
              const has = found.includes(id)
              const d = cache[id]
              return (
                <li key={id} style={{ ['--tilt' as string]: `${((i * 37) % 7) - 3}deg` }}>
                  <button
                    type="button"
                    disabled={!has}
                    className={`${styles.item} ${has ? styles.have : styles.lost} ${selected === id ? styles.sel : ''}`}
                    onClick={() => { setSelected(id); setDocIdx(0) }}
                    aria-label={has ? (d?.title ?? id) : '아직 확보하지 못한 증거'}
                  >
                    <span className={styles.no}>{id}</span>
                    {has ? <FileText size={28} /> : <Lock size={24} />}
                    <span className={styles.name}>{has ? (d?.title ?? '불러오는 중…') : '잠김 · 인물과 대화해 단서 찾기'}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>

        <aside className={styles.viewer} aria-label="증거 상세">
          {!detail ? (
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
                <div><dt>획득 경로</dt><dd>{detail.acquiredBy ? ROUTE_LABEL[detail.acquiredBy] : "서버 기록 미제공"}</dd></div>
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
