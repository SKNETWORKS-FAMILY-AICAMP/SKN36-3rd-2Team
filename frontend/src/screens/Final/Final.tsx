import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import CharacterPortrait from '../../components/CharacterPortrait'
import { npcName } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import { NOTE_SECTIONS, useNoteStore } from '../../store/noteStore'
import styles from './Final.module.css'

const RESULT_LABEL = { FULL: '사건 해결', ESTIMATED: '추정 성립', WRONG: '지목 실패', NOT_ENOUGH_EVIDENCE: '단서 부족' } as const

export default function Final() {
  const navigate = useNavigate()
  const final = useGameStore((s) => s.final)
  const session = useGameStore((s) => s.session)
  const starting = useGameStore((s) => s.starting)
  const ensure = useGameStore((s) => s.ensureSession)
  const recoverEnding = useGameStore((s) => s.recoverEnding)
  const endingError = useGameStore((s) => s.endingError)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    void ensure().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : '세션 조회에 실패했습니다.')
    })
  }, [ensure])
  const evidence = useGameStore((s) => s.evidence)
  const reset = useGameStore((s) => s.resetGame)
  const notes = useNoteStore((s) => s.notes)

  // A completed game can be opened after refresh even if local final data was lost.
  if (!final) {
    if (session?.phase === 'FINISHED') {
      return (
        <div className={styles.page}>
          <main className={styles.wrap}>
            <p className={styles.kicker}>CASE 001 · 사건 종료</p>
            <h1 className="serif">엔딩 확인</h1>
            <p className={styles.ending}>{endingError ?? '서버에서 엔딩 정보를 불러오는 중입니다.'}</p>
            <button type="button" className="btn" onClick={() => void recoverEnding(session)}>엔딩 다시 불러오기</button>
          </main>
        </div>
      )
    }
    if (!session || starting || loadError) {
      return (
        <div className={styles.page}>
          <main className={styles.wrap}>
            <p className={styles.ending}>{loadError ?? '게임 기록을 확인하는 중입니다.'}</p>
            {loadError && <button type="button" className="btn" onClick={() => { setLoadError(null); void ensure().catch((error: unknown) => setLoadError(error instanceof Error ? error.message : '세션 조회 실패')) }}>다시 시도</button>}
          </main>
        </div>
      )
    }
    return <Navigate to="/accuse" replace />
  }
  const { response, suspectId, evidenceIds } = final
  // 서버가 엔딩을 주지 않은 경우(마지막 기회 소진 등)를 위한 기본 문구
  const ending = response.ending ?? {
    title: response.result === 'FULL' ? '사건 종결' : '진실은 어둠 속에 남았다',
    text: response.result === 'FULL' || response.result === 'ESTIMATED'
      ? '수사가 마무리되었습니다.'
      : '모든 지목 기회를 사용했습니다. 이번 수사에서는 사건의 진실에 닿지 못했습니다.',
  }

  return (
    <div className={`${styles.page} ${styles[response.result] ?? ''} ${response.endingKind === 'DEEP' ? styles.DEEP : ''}`}>
      <motion.div className={styles.wrap} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.4 }}>
        <p className={styles.kicker}>CASE 001 · 마지막 기록: 졸업하지 못한 밤</p>
        <h1 className="serif">{ending.title}</h1>
        <p className={styles.verdict}>
          판정 · {RESULT_LABEL[response.result]}
          {response.endingKind === 'DEEP' && <span className={styles.deep}>심화 엔딩</span>}
        </p>
        <p className={styles.ending}>{ending.text}</p>

        {endingError && session?.phase === 'FINISHED' && (
          <div role="alert">
            <p>{endingError}</p>
            <button type="button" className="btn" onClick={() => void recoverEnding(session)}>엔딩 상세 다시 불러오기</button>
          </div>
        )}

        {/* Private case truth is rendered only when the server declares SUCCESS. */}
        {response.result === 'FULL' && response.truth && (
          <section className={styles.truth} aria-label="사건의 진실">
            <h2 className="serif">사건의 진실</h2>
            <dl>
              <div><dt>범인</dt><dd>{npcName(response.truth.perpetratorId)}</dd></div>
              <div><dt>동기</dt><dd>{response.truth.motive}</dd></div>
              <div><dt>사망 원인</dt><dd>{response.truth.causeOfDeath}</dd></div>
              <div><dt>범행 수법</dt><dd>{response.truth.crimeMethod}</dd></div>
            </dl>
          </section>
        )}

        <section className={styles.cols}>
          <div className={styles.accused}>
            <h2>나의 지목</h2>
            {suspectId ? <CharacterPortrait id={suspectId} alt="" className={styles.face} /> : null}
            <b className="serif">{suspectId ? npcName(suspectId) : '지목 기록을 복구하지 못했습니다.'}</b>
            <ul>
              {evidenceIds.map((id) => <li key={id}><span>{id}</span> {final.evidenceTitles?.[id] ?? evidence[id]?.title ?? ''}</li>)}
            </ul>
          </div>

          <div className={styles.record}>
            <h2>나의 최종 추리 기록</h2>
            <p className={styles.sub}>직접 쓴 노트가 그대로 표시됩니다. 판정과는 관계없습니다.</p>
            {NOTE_SECTIONS.map((s, i) => (
              <article key={s.key}>
                <h3><b>{i + 1}</b> {s.title}</h3>
                <p>{notes[s.key].trim() || '작성하지 않았습니다.'}</p>
              </article>
            ))}
          </div>
        </section>

        <button type="button" className="btn" onClick={() => { reset(); navigate('/') }}>처음으로</button>
      </motion.div>
    </div>
  )
}
