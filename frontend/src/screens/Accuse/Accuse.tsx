import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Lock } from 'lucide-react'
import TopNav from '../../components/TopNav'
import CharacterPortrait from '../../components/CharacterPortrait'
import { NPC_PUBLIC, npcName } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import { isGameOver, type AccuseResponse } from '../../api/types'
import styles from './Accuse.module.css'

export default function Accuse() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const final = useGameStore((s) => s.final)
  const cache = useGameStore((s) => s.evidence)
  const loadEvidence = useGameStore((s) => s.loadEvidence)
  const accuse = useGameStore((s) => s.accuse)

  const [suspect, setSuspect] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [miss, setMiss] = useState<AccuseResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { void ensure() }, [ensure])
  const found = session?.foundEvidence ?? []
  const key = found.join()
  useEffect(() => { found.forEach((id) => void loadEvidence(id)) /* eslint-disable-next-line */ }, [key, session?.sessionId])

  if (final || session?.phase === 'FINISHED') return <Navigate to="/final" replace />

  const unlocked = session?.unlockedNpcs ?? []
  const can = !!session?.canAccuse
  const ready = can && !!suspect && picked.length >= 1 && picked.length <= 3 && !busy

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 3 ? p : [...p, id]))

  const submit = async () => {
    if (!suspect || busy) return
    setBusy(true); setError(null)
    try {
      const res = await accuse(suspect, picked)
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
            <p>지목할 인물과 추리 기록에 남길 증거(1~3개)를 고르세요. 실제 판정은 서버가 보유한 증거를 기준으로 진행됩니다.</p>
          </div>
          <div className={styles.chances} aria-label={`남은 기회 ${session?.attemptsLeft ?? 0}번`}>
            남은 기회
            <span>{Array.from({ length: 3 }, (_, i) => <i key={i} className={i < (session?.attemptsLeft ?? 0) ? styles.live : ''} />)}</span>
          </div>
        </header>

        {!can && (
          <p className={styles.gate}>
            <Lock size={15} /> 아직 지목할 수 없습니다. 확보한 증거 {found.length}개 · 만난 인물 {unlocked.length}명.
            <br />① 인물 대화에서 사건 당일 행적·관계를 질문하고 ② 가진 증거를 제시해 반응을 보면 새 증거와 인물이 열립니다.
          </p>
        )}

        <section aria-label="지목할 인물">
          <h2>1. 지목할 인물</h2>
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

        <section aria-label="근거 증거">
          <h2>2. 근거 증거 <small>({picked.length}/3)</small></h2>
          {found.length === 0 ? (
            <p className={styles.none}>확보한 증거가 없습니다.</p>
          ) : (
            <ul className={styles.evs}>
              {found.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    disabled={!can}
                    className={`${styles.ev} ${picked.includes(id) ? styles.on : ''}`}
                    onClick={() => toggle(id)}
                    aria-pressed={picked.includes(id)}
                  >
                    {picked.includes(id) && <Check size={16} className={styles.tick} />}
                    <b>{id}</b>
                    <span>{cache[id]?.title ?? ''}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {error && <p className={styles.err} role="alert">{error}</p>}
      </main>
      <div className={`${styles.dock} panel`} role="region" aria-label="선택 요약">
        <p className={styles.dockText}>
          <span>지목 <b>{suspect ? npcName(suspect) : '— 인물을 고르세요'}</b></span>
          <span>근거 <b>{picked.length > 0 ? picked.join(' · ') : '— 증거를 1~3개 고르세요'}</b> <small>({picked.length}/3)</small></span>
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
                  <p>선택한 증거는 추리 기록에 남습니다. 지목 조건을 충족하면 기회가 한 번 줄어듭니다.</p>
                  <ul className={styles.sum}>
                    {picked.map((id) => <li key={id}><b>{id}</b> {cache[id]?.title ?? ''}</li>)}
                  </ul>
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
                      <p>남은 기회 {miss.attemptsLeft}번. 더 조사하고 다시 판단하세요. 방금 고른 인물과 증거는 그대로 남아 있으니 바꾸고 싶은 것만 고치면 됩니다.</p>
                    </>
                  )}
                  <div className={styles.row}>
                    <button type="button" className="btn btn--primary" onClick={() => setMiss(null)}>
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
