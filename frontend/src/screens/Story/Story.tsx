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
  useEffect(() => { void ensure() }, [ensure])
  const [beat, setBeat] = useState(() => {
    try { return Number(localStorage.getItem('serin-story-beat')) || 0 } catch { return 0 }
  })
  const [place, setPlace] = useState<(typeof PLACES)[number] | null>(null)
  const [seen, setSeen] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('serin-seen-places') ?? '[]') as string[] } catch { return [] }
  })
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
