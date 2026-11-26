import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Lock } from 'lucide-react'
import TopNav from '../../components/TopNav'
import CharacterPortrait from '../../components/CharacterPortrait'
import { NPC_PUBLIC, npcName } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import { api } from '../../api/client'
import { ApiHttpError } from '../../api/httpApi'
import { isExpandedSession, isGameOver, type AccuseResponse, type ReconstructionAxis, type ReconstructionSelections } from '../../api/types'
import styles from './Accuse.module.css'

const RECON_ERROR: Record<number, string> = {
  403: '지금은 재구성을 제출할 수 없습니다. 보유하지 않은 증거가 포함됐을 수 있습니다.',
  409: '게임 상태가 바뀌었습니다. 다시 제출해 주세요.',
  422: '항목마다 증거를 2~3개씩, 3개 항목 이상 골라 주세요.',
  503: '재구성 기능을 지금 사용할 수 없습니다.',
}

const RECON_AXES: { key: ReconstructionAxis; label: string }[] = [
  { key: 'motive', label: '동기' },
  { key: 'access', label: '접근' },
  { key: 'timeline', label: '시간' },
  { key: 'coverup', label: '은폐' },
]

export default function Accuse() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const final = useGameStore((s) => s.final)
  const accuse = useGameStore((s) => s.accuse)

  const [quitting, setQuitting] = useState(false)
  const giveUp = useGameStore(s => s.giveUp)
  const [suspect, setSuspect] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [miss, setMiss] = useState<AccuseResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  // 사건 재구성: 항목별로 고른 증거 ID. accepted = 서버가 재구성을 인정함
  const [recon, setRecon] = useState<ReconstructionSelections>({})
  const [reconResult, setReconResult] = useState<'accepted' | 'rejected' | null>(null)
  const evidence = useGameStore((s) => s.evidence)
  const refresh = useGameStore((s) => s.refresh)
  const loadEvidence = useGameStore((s) => s.loadEvidence)
  const showRecon = session?.currentChapter === 'CH04' && session.phase === 'INVESTIGATION'
  // 재구성 칩에 증거 이름을 보여주려고 보유 증거 상세를 불러온다 (이미 받은 건 캐시)
  const foundKey = (session?.foundEvidence ?? []).join(',')
  useEffect(() => {
    if (showRecon) session?.foundEvidence.forEach((id) => void loadEvidence(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRecon, foundKey])

  useEffect(() => { void ensure() }, [ensure])
  const found = session?.foundEvidence ?? []

  if (final || session?.phase === 'FINISHED') return <Navigate to="/final" replace />

  const unlocked = session?.unlockedNpcs ?? []
  const can = !!session?.canAccuse
  const ready = can && !!suspect && unlocked.includes(suspect) && !busy

  const quit = async (suspectId: string, previous?: AccuseResponse) => {
    setBusy(true); setError(null)
    const message = await giveUp(suspectId, previous)
    // 성공하면 final이 생기면서 최종 화면으로 넘어간다
    if (message) { setError(message); setMiss(null); setQuitting(false) }
    setBusy(false)
  }

  const filled = RECON_AXES.filter(({ key }) => (recon[key]?.length ?? 0) >= 2)
  const togglePick = (axis: ReconstructionAxis, id: string) => {
    setReconResult(null)
    setRecon((cur) => {
      const list = cur[axis] ?? []
      const next = list.includes(id) ? list.filter((x) => x !== id) : list.length < 3 ? [...list, id] : list
      return { ...cur, [axis]: next }
    })
  }
  const submitRecon = async () => {
    if (!session || busy) return
    setBusy(true); setError(null)
    try {
      // 2개 이상 고른 항목만 보낸다 (서버 규칙: 항목당 2~3개, 3항목 이상)
      const selections = Object.fromEntries(filled.map(({ key }) => [key, recon[key]!]))
      setReconResult((await api.reconstruct(session.sessionId, selections)) ? 'accepted' : 'rejected')
    } catch (e) {
      const status = e instanceof ApiHttpError ? e.status : 0
      setError(RECON_ERROR[status] ?? '재구성을 제출하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setBusy(false)
    }
    await refresh().catch(() => undefined)
  }

  const submit = async () => {
    if (!suspect || busy) return
    setBusy(true); setError(null)
    try {
      const res = await accuse(suspect, [])
      setConfirm(false)
      if (isGameOver(res)) navigate('/final')
      else setMiss(res)
    } catch (e) {
      setConfirm(false)
      setError(e instanceof Error ? e.message : '지목에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.page}>
      <TopNav />
      <main className={styles.main}>
        <header className={`${styles.head} page-head`}>
          <div>
            <h1 className="serif">범인 지목</h1>
            <p>범인으로 지목할 인물을 한 명 선택하세요. 지목 자격은 서버에 수집된 증거를 기준으로 검증합니다.</p>
          </div>
          <div className={styles.chances} aria-label={`남은 기회 ${session?.attemptsLeft ?? 0}번`}>
            남은 기회
            <span>{Array.from({ length: 3 }, (_, i) => <i key={i} className={i < (session?.attemptsLeft ?? 0) ? styles.live : ''} />)}</span>
          </div>
        </header>

        {!can && (
          <p className={styles.gate}>
            <Lock size={15} /> {session?.phase === 'PROLOGUE' ? '프롤로그를 마쳐야 지목할 수 있습니다.' : isExpandedSession(session) ? '지목하려면 증거 수와 수집 점수가 각각 절반 이상이어야 합니다.' : '지목하려면 증거 5개 이상과 수집 점수 11점 이상이 필요합니다.'} 현재 {session?.collection.score ?? 0}점 · 확보한 증거 {found.length}개 · 만난 인물 {unlocked.length}명.
            <br />① 인물 대화에서 사건 당일 행적·관계를 질문하고 ② 가진 증거를 제시해 반응을 보면 새 증거와 인물이 열립니다.
          </p>
        )}

        {showRecon && (
          <section aria-label="사건 재구성" className={styles.recon}>
            <h2>사건 재구성</h2>
            <p>항목마다 근거가 되는 증거를 2~3개 고르세요. 3개 항목 이상 채우면 제출할 수 있습니다. 재구성 없이도 지목할 수 있습니다.</p>
            {reconResult !== 'accepted' && RECON_AXES.map(({ key, label }) => (
              <div key={key} className={styles.reconRow}>
                <span className={styles.reconLabel}>{label} <small>{recon[key]?.length ?? 0}/3</small></span>
                <div className={styles.reconChips}>
                  {found.map((id) => (
                    <button key={id} type="button" aria-pressed={recon[key]?.includes(id) ?? false}
                      className={recon[key]?.includes(id) ? styles.chipOn : ''} onClick={() => togglePick(key, id)} disabled={busy}>
                      {id} {evidence[id]?.title ?? ''}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className={styles.row}>
              {reconResult && <span role="status">{reconResult === 'accepted' ? '재구성이 확인되었습니다.' : '재구성이 성립하지 않았습니다. 증거 조합을 다시 살펴보세요.'}</span>}
              {reconResult !== 'accepted' && <button type="button" className="btn btn--primary" disabled={busy || filled.length < 3} onClick={() => void submitRecon()}>재구성 제출</button>}
            </div>
          </section>
        )}

        <section aria-label="지목할 인물">
          <h2>범인으로 지목할 인물</h2>
          <ul className={styles.people}>
            {NPC_PUBLIC.map((n) => {
              const open = unlocked.includes(n.id)
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    disabled={!open || !can}
                    className={`${styles.person} ${suspect === n.id ? styles.on : ''}`}
                    onClick={() => setSuspect(n.id)}
                    aria-pressed={suspect === n.id}
                  >
                    {open ? <CharacterPortrait id={n.id} alt="" /> : <span className={styles.sil}><Lock size={20} /></span>}
                    <span>{open ? n.name : '???'}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>



        {session && !busy && !(isExpandedSession(session) && can) && <section>
          {quitting ? <><p>이번 수사를 여기서 끝내고 엔딩을 확인할까요?</p>
            <button className="btn" onClick={() => setQuitting(false)}>계속 조사</button>
            <button className="btn btn--danger" onClick={() => void quit('')}>수사 종료 확정</button></>
            : <button className="btn" onClick={() => setQuitting(true)}>수사 포기</button>}
        </section>}
        {error && <p className={styles.err} role="alert">{error}</p>}
      </main>
      <div className={`${styles.dock} panel`} role="region" aria-label="선택 요약">
        <p className={styles.dockText}>
          <span>지목 <b>{suspect ? npcName(suspect) : '— 인물을 고르세요'}</b></span>
        </p>
        <button type="button" className="btn btn--danger" disabled={!ready} onClick={() => setConfirm(true)}>
          지목하기
        </button>
      </div>

      <AnimatePresence>
        {(confirm || miss) && (
          <motion.div className={styles.backdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className={`${styles.modal} panel`} role="dialog" aria-modal="true" initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
              {confirm ? (
                <>
                  <h3 className="serif">{suspect ? npcName(suspect) : ''}을(를) 지목하시겠습니까?</h3>
                  <p>이 인물을 범인으로 지목하시겠습니까? 지목이 성립하면 기회가 한 번 차감됩니다.</p>
                  <div className={styles.row}>
                    <button type="button" className="btn" onClick={() => setConfirm(false)} disabled={busy}>다시 생각한다</button>
                    <button type="button" className="btn btn--danger" onClick={() => void submit()} disabled={busy}>
                      {busy ? '판정 중…' : '지목 확정'}
                    </button>
                  </div>
                </>
              ) : miss && (
                <>
                  {miss.result === 'NOT_ENOUGH_EVIDENCE' ? (
                    <>
                      <h3 className="serif">단서가 더 필요합니다</h3>
                      <p>아직 지목할 만큼 단서가 모이지 않았습니다. 기회는 줄어들지 않았습니다.</p>
                    </>
                  ) : (
                    <>
                      <h3 className="serif">이 지목은 성립하지 않았습니다</h3>
                      <p>남은 기회 {miss.attemptsLeft}번. 더 조사하고 다시 판단하세요. 다른 인물을 지목하려면 선택을 변경하세요.</p>
                    </>
                  )}
                  <div className={styles.row}>
                    {/* 확장판은 지목 조건을 채우면 서버가 포기를 받지 않아 버튼을 숨긴다 */}
                    {!(isExpandedSession(session) && can) && (
                      <button type="button" className="btn btn--primary" onClick={() => void quit(suspect ?? '', miss)} disabled={busy}>이대로 엔딩 보기</button>
                    )}
                    <button type="button" className="btn" onClick={() => setMiss(null)}>
                      돌아가기
                    </button>
                  </div>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
