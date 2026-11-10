import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import Reveal from './Reveal'
import { ALBUM, GROUP_PHOTO } from '../../data/characters'
import {
  ALBUM_TEXT, CASE_INTRO, PHOTO_CAPTION, TIMELINE_LINES,
} from '../../data/publicData'
import { useGameStore } from '../../store/gameStore'
import { api } from '../../api/client'
import styles from './Main.module.css'

type Stage = 'poster' | 'album' | 'group' | 'timeline' | 'intro'

export default function Main() {
  const [stage, setStage] = useState<Stage>('poster')
  const reduce = useReducedMotion()
  const startGame = useGameStore((s) => s.startGame)
  const navigate = useNavigate()

  const fade = reduce ? 0 : 0.7
  const toIntro = useCallback(() => setStage('intro'), [])

  const [saved, setSaved] = useState(false)
  const [askNew, setAskNew] = useState(false)
  const [busy, setBusy] = useState(false)

  // 이전에 하던 게임이 서버에 남아 있으면 이어하기를 보여준다 (조용히 확인, 실패하면 숨김)
  useEffect(() => {
    let alive = true
    let sid: string | null = null
    try { sid = localStorage.getItem('serin-session-id') } catch { /* ignore */ }
    if (sid) {
      api.getState(sid).then(() => { if (alive) setSaved(true) }).catch(() => { /* 없음 */ })
    }
    return () => { alive = false }
  }, [])

  const resume = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await useGameStore.getState().ensureSession()
      if (!useGameStore.getState().session) throw new Error('이어할 게임을 불러오지 못했습니다.')
      navigate(useGameStore.getState().final ? '/final' : '/story')
    } catch (e) {
      setError(e instanceof Error ? e.message : '이어할 게임을 불러오지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }, [busy, navigate])
  const [error, setError] = useState<string | null>(null)

  // 세션 생성이 끝난 뒤에만 다음 화면으로 넘어간다. 실패하면 메인에 남아 다시 시도한다.
  const begin = useCallback(async (confirmed = false) => {
    if (busy) return
    if (saved && !confirmed) { setAskNew(true); return }
    setAskNew(false)
    setBusy(true)
    setError(null)
    try {
      await startGame()
      if (!useGameStore.getState().session) throw new Error('세션을 만들지 못했습니다.')
      setStage('album')
    } catch (e) {
      setError(e instanceof Error ? e.message : '게임을 시작하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }, [busy, saved, startGame])

  // 포스터에서 Enter/Space 로도 시작
  useEffect(() => {
    if (stage !== 'poster' || saved) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        void begin()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stage, saved, begin])

  return (
    <main className={styles.root}>
      <AnimatePresence mode="wait">
        <motion.section
          key={stage}
          className={styles.stage}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: fade, ease: 'easeInOut' }}
        >
          {stage === 'poster' && (
            <>
              <Reveal onStart={() => void begin()} onResume={saved ? () => void resume() : undefined} />
              {askNew && (
                <div className={styles.askBackdrop} role="dialog" aria-modal="true" aria-label="새로 시작 확인">
                  <div className={`${styles.ask} panel`}>
                    <h3 className="serif">새로 시작하시겠습니까?</h3>
                    <p>진행 중이던 조사 기록과 추리 노트가 사라집니다.</p>
                    <div className={styles.askRow}>
                      <button type="button" className="btn" onClick={() => setAskNew(false)}>이어서 한다</button>
                      <button type="button" className="btn btn--danger" onClick={() => void begin(true)}>새로 시작</button>
                    </div>
                  </div>
                </div>
              )}
              {error && (
                <p role="alert" className={styles.startError}>
                  {error} 다시 시도하세요.
                </p>
              )}
            </>
          )}
          {stage === 'album' && (
            <Album reduce={!!reduce} onNext={() => setStage('group')} onSkip={toIntro} />
          )}
          {stage === 'group' && (
            <Group onNext={() => setStage('timeline')} onSkip={toIntro} />
          )}
          {stage === 'timeline' && (
            <Timeline reduce={!!reduce} onNext={toIntro} onSkip={toIntro} />
          )}
          {stage === 'intro' && <Intro reduce={!!reduce} onStart={() => navigate('/story')} />}
        </motion.section>
      </AnimatePresence>
    </main>
  )
}

function SkipButton({ onSkip }: { onSkip: () => void }) {
  return (
    <button type="button" className={styles.skip} onClick={onSkip}>
      인트로 건너뛰기
    </button>
  )
}

/* ② 졸업앨범 */
function Album({ reduce, onNext, onSkip }: { reduce: boolean; onNext: () => void; onSkip: () => void }) {
  const total = ALBUM.length
  return (
    <div className={styles.albumWrap}>
      <SkipButton onSkip={onSkip} />
      <motion.div
        className={styles.albumPage}
        initial={reduce ? false : { opacity: 0, rotateX: -16, y: 24, transformPerspective: 1400 }}
        animate={{ opacity: 1, rotateX: 0, y: 0 }}
        transition={{ duration: reduce ? 0 : 1.1, ease: [0.22, 0.61, 0.36, 1] }}
        style={{ transformOrigin: 'top center' }}
      >
        <header className={styles.albumHead}>
          <div className={styles.tag}>
            <strong className="serif">{ALBUM_TEXT.titleKo}</strong>
            <span>{ALBUM_TEXT.titleEn}</span>
          </div>
          <motion.p
            className={`serif ${styles.quote}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: reduce ? 0 : 0.4 + total * 0.18, duration: reduce ? 0 : 1.2 }}
          >
            {ALBUM_TEXT.quote}
          </motion.p>
          <p className={styles.albumNote}>앨범 속 12명 중 10명이 이번 사건의 조사 대상입니다.</p>
        </header>
        <ul className={styles.grid}>
          {ALBUM.map((p, i) => (
            <motion.li
              key={p.id}
              className={`${styles.tile} ${p.highlight ? styles.tileHighlight : ''}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: reduce ? 0 : 0.25 + i * 0.18, duration: reduce ? 0 : 0.7 }}
            >
              <img src={p.tile} alt={p.name} draggable={false} />
              <span className={`serif ${styles.nameTag}`}>{p.name}</span>
            </motion.li>
          ))}
        </ul>
      </motion.div>
      <motion.button
        type="button"
        className={styles.next}
        onClick={onNext}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: reduce ? 0 : 0.8 + total * 0.18, duration: reduce ? 0 : 0.8 }}
      >
        다음 ▸
      </motion.button>
    </div>
  )
}

/* ③ 단체사진 */
function Group({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  return (
    <div className={styles.groupWrap}>
      <SkipButton onSkip={onSkip} />
      <figure className={styles.photoFrame}>
        <img src={GROUP_PHOTO} alt="2016년 졸업반 단체사진" draggable={false} />
        <figcaption className="serif">{PHOTO_CAPTION}</figcaption>
      </figure>
      <button type="button" className={styles.next} onClick={onNext}>
        다음 ▸
      </button>
    </div>
  )
}

/* ④ 시간 자막: 2016 → 2026 */
function Timeline({ reduce, onNext, onSkip }: { reduce: boolean; onNext: () => void; onSkip: () => void }) {
  const step = reduce ? 0 : 1.8
  return (
    <div className={styles.timelineWrap}>
      <SkipButton onSkip={onSkip} />
      <div className={styles.timelineLines}>
        {TIMELINE_LINES.map((line, i) => (
          <motion.p
            key={line}
            className={`serif ${styles.timelineLine}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 + i * step, duration: reduce ? 0 : 1 }}
          >
            {line}
          </motion.p>
        ))}
      </div>
      <motion.button
        type="button"
        className={styles.next}
        onClick={onNext}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 + TIMELINE_LINES.length * step, duration: reduce ? 0 : 0.8 }}
      >
        다음 ▸
      </motion.button>
    </div>
  )
}

/* ⑤ 사건 시작 안내 */
function Intro({ reduce, onStart }: { reduce: boolean; onStart: () => void }) {
  const notes = useGameStore((s) => s.notes)
  const list = notes.length ? notes : CASE_INTRO.notes
  const d = (n: number) => (reduce ? 0 : n)
  return (
    <div className={styles.introWrap}>
      <button type="button" className={styles.skip} onClick={onStart}>
        바로 조사 시작 ▸
      </button>
      <article className={styles.file}>
        <p className={styles.stamp}>CASE 001</p>
        <h2 className={`serif ${styles.fileHead}`}>[ {CASE_INTRO.heading} ]</h2>
        <div className={styles.fileBody}>
          {CASE_INTRO.lines.map((line, i) => (
            <motion.p
              key={line}
              className="serif"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: d(0.5 + i * 0.9), duration: d(0.9) }}
            >
              {line}
            </motion.p>
          ))}
        </div>
        <motion.ul
          className={`mono ${styles.memo}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: d(0.5 + CASE_INTRO.lines.length * 0.9), duration: d(0.9) }}
        >
          {list.map((n) => (
            <li key={n.id}>
              <b>현장 메모 {n.id}</b> {n.text}
            </li>
          ))}
        </motion.ul>
        <motion.p
          className={`serif ${styles.closing}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: d(1 + (CASE_INTRO.lines.length + 1) * 0.9), duration: d(1) }}
        >
          {CASE_INTRO.closing}
        </motion.p>
        <motion.button
          type="button"
          className={styles.startCase}
          onClick={onStart}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: d(2 + (CASE_INTRO.lines.length + 1) * 0.9), duration: d(0.8) }}
        >
          조사 시작
        </motion.button>
      </article>
    </div>
  )
}
