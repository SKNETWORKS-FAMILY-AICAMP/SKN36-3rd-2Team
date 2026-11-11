import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import TopNav from '../../components/TopNav'
import PosterScene from '../../components/PosterScene'
import PlaceScene from '../../components/PlaceScene'
import { useGameStore } from '../../store/gameStore'
import { CASE_INTRO } from '../../data/publicData'
import styles from './Story.module.css'

const OPENING = [
  '2026.10.17 · 세린국제학교 구 본관 · 밤',
  '신기범이 발견된 건물 안은 조용하다. 창밖에서는 빗소리가 아직 이어진다.',
  '수사관은 먼저 현장을 둘러보기로 한다.',
]

const PLACES = [
  { key: 'lobby', name: '1층 로비', text: '불이 꺼진 로비. 동창회를 위해 마련된 접수 자리가 그대로 남아 있다.' },
  { key: 'stairs', name: '내부 계단', text: '신기범이 발견된 계단 아래에는 통제선이 둘러져 있다. 추락인지 타살인지는 초기 관찰만으로 확정되지 않았다.' },
  { key: 'records', name: '2층 기록실 입구', text: CASE_INTRO.notes[0].text },
  { key: 'office', name: '신기범 사무실', text: CASE_INTRO.notes[1].text },
] as const

export default function Story() {
  const navigate = useNavigate()
  const first = useGameStore((s) => s.session?.unlockedNpcs[0]) ?? 'C01'
  const ensure = useGameStore((s) => s.ensureSession)
  const [beat, setBeat] = useState(() => {
    try { return Number(localStorage.getItem('serin-story-beat')) || 0 } catch { return 0 }
  })
  const [sessionReady, setSessionReady] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [place, setPlace] = useState<(typeof PLACES)[number] | null>(null)
  const [seen, setSeen] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('serin-seen-places') ?? '[]') as string[] } catch { return [] }
  })
  // 서버 세션 확인/재생성 후 진행 기록을 다시 읽습니다.
  // 새 세션이 만들어지면 gameStore가 이전 브라우저 기록을 초기화합니다.
  useEffect(() => {
    let active = true
    void ensure().then(() => {
      if (!active) return
      if (!useGameStore.getState().session) {
        throw new Error('게임 세션을 불러오지 못했습니다.')
      }
      try {
        const raw = Number(localStorage.getItem('serin-story-beat') ?? '0')
        setBeat(Number.isFinite(raw) ? Math.max(0, Math.min(raw, OPENING.length)) : 0)
      } catch { setBeat(0) }
      try {
        const raw: unknown = JSON.parse(localStorage.getItem('serin-seen-places') ?? '[]')
        const allowed = new Set<string>(PLACES.map((p) => p.key))
        setSeen(Array.isArray(raw) ? raw.filter((k): k is string => typeof k === 'string' && allowed.has(k)) : [])
      } catch { setSeen([]) }
      setSessionReady(true)
    }).catch((error: unknown) => {
      if (active) setSessionError(error instanceof Error ? error.message : '서버 연결에 실패했습니다.')
    })
    return () => { active = false }
  }, [ensure])
  const [photoMissing, setPhotoMissing] = useState(false)
  const intro = beat < OPENING.length

  const next = () => setBeat((b) => {
    const n = Math.min(b + 1, OPENING.length)
    try { localStorage.setItem('serin-story-beat', String(n)) } catch { /* ignore */ }
    return n
  })
  const skipIntro = () => setBeat(() => {
    try { localStorage.setItem('serin-story-beat', String(OPENING.length)) } catch { /* ignore */ }
    return OPENING.length
  })
  const visit = (p: (typeof PLACES)[number]) => {
    setPlace(p)
    setSeen((s) => {
      const n = s.includes(p.key) ? s : [...s, p.key]
      try { localStorage.setItem('serin-seen-places', JSON.stringify(n)) } catch { /* ignore */ }
      return n
    })
  }

  if (!sessionReady) {
    return (
      <div className={styles.page}>
        <TopNav />
        <main className={styles.main}>
          <section className={styles.box} role={sessionError ? 'alert' : 'status'}>
            <p className={styles.line}>{sessionError ?? '사건 기록을 불러오는 중입니다.'}</p>
            {sessionError && (
              <button type="button" className={styles.go} onClick={() => navigate('/')}>
                메인 화면으로
              </button>
            )}
          </section>
        </main>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <AnimatePresence mode="sync">
        <motion.div
          key={place?.key ?? 'outside'}
          className={styles.bg}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6 }}
        >
          {place ? <PlaceScene place={place.key} /> : <PosterScene />}
        </motion.div>
      </AnimatePresence>
      <div className={styles.dim} />
      <TopNav />
      <AnimatePresence>
        {place?.key === 'stairs' && !photoMissing && (
          <motion.figure
            key="scene-photo"
            className={styles.scenePhoto}
            initial={{ opacity: 0, y: 10, rotate: 4 }}
            animate={{ opacity: 1, y: 0, rotate: 2 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            <img
              src={`${import.meta.env.BASE_URL}assets/scene/victim_stairs.webp`}
              alt="사건 현장 사진 — 내부 계단 아래"
              draggable={false}
              onError={() => setPhotoMissing(true)}
            />
            <figcaption>사건 현장</figcaption>
          </motion.figure>
        )}
      </AnimatePresence>
      <main className={styles.main}>
        <AnimatePresence mode="wait">
          {intro ? (
            <motion.div
              key={`b${beat}`}
              className={styles.box}
              role="button"
              tabIndex={0}
              onClick={next}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); next() } }}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
            >
              <p className={beat === 0 ? styles.place : styles.line}>{OPENING[beat]}</p>
              <span className={styles.more}>클릭하여 계속 ▾</span>
              <button
                type="button"
                className={styles.skipBtn}
                onClick={(e) => { e.stopPropagation(); skipIntro() }}
              >
                도입부 건너뛰기 ▸
              </button>
            </motion.div>
          ) : (
            <motion.div key="choose" className={styles.box} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
              <p className={styles.place}>
                어디를 살펴볼까? <span className={styles.count}>살펴본 곳 {seen.length} / {PLACES.length}</span>
              </p>
              <div className={styles.places}>
                {PLACES.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    className={`${styles.pl} ${place?.key === p.key ? styles.cur : ''}`}
                    onClick={() => visit(p)}
                  >
                    {p.name}
                    {seen.includes(p.key) ? <small> ✓</small> : <i className={styles.new} aria-label="아직 살펴보지 않음" />}
                  </button>
                ))}
              </div>
              <p className={styles.obs} aria-live="polite">{place ? place.text : '장소를 선택하면 관찰한 내용이 표시됩니다.'}</p>
              <div className={styles.actions}>
                {seen.length < PLACES.length && (
                  <span className={styles.left}>아직 살펴보지 않은 곳이 {PLACES.length - seen.length}곳 남아 있습니다.</span>
                )}
                <button type="button" className={styles.go} onClick={() => navigate(`/chat/${first}`)}>
                  관계자에게 이야기를 듣는다
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
