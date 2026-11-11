
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'

import TopNav from '../../components/TopNav'
import PosterScene from '../../components/PosterScene'
import PlaceScene from '../../components/PlaceScene'
import GameHelp from '../../components/GameHelp'
import VisualNovelDialogue from '../../components/VisualNovelDialogue'

import { useGameStore } from '../../store/gameStore'
import { CASE_INTRO } from '../../data/publicData'
import styles from './Story.module.css'

// ============================================================
// Issue #59 — Cinematic Prologue + Tutorial
// ============================================================

const STORY_KEY = 'serin-story-beat-v2'
const HELP_SEEN_KEY = 'serin-help-seen-session-v2'
const SEEN_PLACES_KEY = 'serin-seen-places'

// ============================================================
// 프롤로그 스토리
// ============================================================

const OPENING = [
  {
    chapter: '2016년 · 마지막 기념사진',
    scene: null,
    text:
      '그때 우리는 모두 같은 사진 속에 있었다. 웃고 있는 얼굴들. 그리고 그날 이후, 누구도 예전처럼 돌아갈 수 없었다.',
  },
  {
    chapter: '2016년 · 사라진 이름',
    scene: null,
    text:
      '2016년 10월 17일. 백서윤이 사라졌다. 사람들은 자발적으로 떠난 것이라 말했다. 그러나 모든 사람이 그 말을 믿은 것은 아니었다.',
  },
  {
    chapter: '10년 후',
    scene: null,
    text:
      '시간이 흐르고, 서로 다른 삶을 살던 사람들이 다시 한 장소로 돌아왔다. 세린국제학교. 오래된 교실과 복도는 그때의 모습을 간직하고 있었다.',
  },
  {
    chapter: '2026년 10월 17일 · 밤',
    scene: 'lobby',
    text:
      '10주년 동창회를 위해 준비된 구 본관. 낮에는 사람들의 목소리로 가득했을 공간이 밤이 되자 낯설게 느껴졌다.',
  },
  {
    chapter: '동창회 · 다시 만난 사람들',
    scene: 'lobby',
    text: '윤태식: 이렇게 다시 모이게 됐군요. 다들 오랜만입니다.',
  },
  {
    chapter: '동창회 · 낯익은 공간',
    scene: 'lobby',
    text: '장현우: 와, 이 건물 정말 그대로네요. 어제 졸업한 것 같은데요?',
  },
  {
    chapter: '동창회 · 오래된 기억',
    scene: 'lobby',
    text: '박도현: 10년이나 지났는데 여긴 거의 변한 게 없네요.',
  },
  {
    chapter: '동창회 · 불편한 공기',
    scene: 'lobby',
    text: '정유라: 그런데 분위기가 조금 이상하지 않아요?',
  },
  {
    chapter: '동창회 · 갑작스러운 소리',
    scene: 'lobby',
    text: '최민석: ……방금 무슨 소리 들으셨습니까?',
  },
  {
    chapter: '사건 발생',
    scene: 'stairs',
    text:
      '그날 밤, 신기범이 본관 내부 계단 아래에서 발견되었다. 현장에 남겨진 물건들은 누군가의 마지막 순간을 말없이 보여주고 있었다.',
  },
  {
    chapter: '내부 계단',
    scene: 'stairs',
    text:
      '깨진 안경. 흩어진 흔적. 단순한 추락이었을까. 아직 단정할 수 있는 것은 아무것도 없었다.',
  },
  {
    chapter: '2층 기록실',
    scene: 'records',
    text:
      '기록실 문은 잠겨 있지 않았다. 누군가 이곳을 드나들었을까. 아니면 처음부터 누군가를 기다리고 있었던 걸까.',
  },
  {
    chapter: '신기범의 사무실',
    scene: 'office',
    text:
      '사무실 서랍에는 누군가 열어본 듯한 흔적이 남아 있었다. 이곳에서 무엇을 찾으려 했는지는 아직 알 수 없었다.',
  },
  {
    chapter: '서로 다른 이야기',
    scene: 'lobby',
    text:
      '사건과 연결된 사람은 열 명. 같은 밤을 보냈지만, 그들이 기억하는 순간은 서로 달랐다. 누군가는 무언가를 숨기고 있을지도 모른다.',
  },
  {
    chapter: 'CASE 001 · 조사 개시',
    scene: null,
    text:
      '기록은 남아 있다. 사람들은 말할 것이다. 이제 당신이 해야 할 일은 그 말들을 하나씩 확인하는 것이다. 먼저 현장을 살펴보자.',
  },
] as const

// ============================================================
// 현장 탐색 데이터
// ============================================================

const PLACES = [
  {
    key: 'lobby',
    name: '1층 로비',
    text:
      '불이 꺼진 로비. 동창회를 위해 마련된 접수 자리가 그대로 남아 있다.',
  },
  {
    key: 'stairs',
    name: '내부 계단',
    text:
      '신기범이 발견된 계단 아래에는 통제선이 둘러져 있다. 추락인지 타살인지는 초기 관찰만으로 확정되지 않았다.',
  },
  {
    key: 'records',
    name: '2층 기록실 입구',
    text: CASE_INTRO.notes[0].text,
  },
  {
    key: 'office',
    name: '신기범 사무실',
    text: CASE_INTRO.notes[1].text,
  },
] as const

type Place = (typeof PLACES)[number]

// ============================================================
// 브라우저 저장 상태
// ============================================================

function loadStoryBeat(): number {
  try {
    const raw = localStorage.getItem(STORY_KEY) ?? '0'
    const value = Number(raw)

    if (!Number.isFinite(value)) return 0

    return Math.max(
      0,
      Math.min(Math.trunc(value), OPENING.length),
    )
  } catch {
    return 0
  }
}

function saveStoryBeat(beat: number): void {
  try {
    localStorage.setItem(STORY_KEY, String(beat))
  } catch {
    // 저장소 오류가 발생해도 게임 진행은 유지합니다.
  }
}

function loadSeenPlaces(): string[] {
  try {
    const raw: unknown = JSON.parse(
      localStorage.getItem(SEEN_PLACES_KEY) ?? '[]',
    )

    if (!Array.isArray(raw)) return []

    const allowed = new Set<string>(
      PLACES.map((place) => place.key),
    )

    return [
      ...new Set(
        raw.filter(
          (key): key is string =>
            typeof key === 'string' && allowed.has(key),
        ),
      ),
    ]
  } catch {
    return []
  }
}

function saveSeenPlaces(places: string[]): void {
  try {
    localStorage.setItem(
      SEEN_PLACES_KEY,
      JSON.stringify(places),
    )
  } catch {
    // 저장소 오류가 발생해도 현장 탐색은 유지합니다.
  }
}

function hasSeenHelp(sessionId: string): boolean {
  try {
    return localStorage.getItem(HELP_SEEN_KEY) === sessionId
  } catch {
    return false
  }
}

function saveHelpSeen(sessionId: string): void {
  try {
    localStorage.setItem(HELP_SEEN_KEY, sessionId)
  } catch {
    // 저장소 오류가 발생해도 NPC 대화로 이동합니다.
  }
}

// ============================================================
// Story Component
// ============================================================

export default function Story() {
  const navigate = useNavigate()

  // ==========================================================
  // 서버 게임 상태
  // ==========================================================

  const session = useGameStore((state) => state.session)
  const ensure = useGameStore((state) => state.ensureSession)

  const sessionId = session?.sessionId ?? null
  const first = session?.unlockedNpcs[0] ?? 'C01'

  // ==========================================================
  // 프롤로그 상태
  // ==========================================================

  const [beat, setBeat] = useState(loadStoryBeat)

  // ==========================================================
  // 서버 세션 상태
  // ==========================================================

  const [sessionReady, setSessionReady] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(
    null,
  )

  // ==========================================================
  // 현장 탐색 상태
  // ==========================================================

  const [place, setPlace] = useState<Place | null>(null)
  const [seen, setSeen] = useState<string[]>(loadSeenPlaces)

  // ==========================================================
  // UI 상태
  // ==========================================================

  const [photoMissing, setPhotoMissing] = useState(false)

  // Issue #59: NPC 대화 전 도움말
  const [helpOpen, setHelpOpen] = useState(false)

  // ==========================================================
  // 서버 세션 확인
  // ==========================================================

  useEffect(() => {
    let active = true

    void ensure()
      .then(() => {
        if (!active) return

        const currentSession = useGameStore.getState().session

        if (!currentSession) {
          throw new Error('게임 세션을 불러오지 못했습니다.')
        }

        // 새 세션이면 저장된 진행 상태가 초기화되어 있습니다.
        setBeat(loadStoryBeat())
        setSeen(loadSeenPlaces())
        setPlace(null)

        setSessionError(null)
        setSessionReady(true)
      })
      .catch((error: unknown) => {
        if (!active) return

        setSessionReady(false)

        setSessionError(
          error instanceof Error
            ? error.message
            : '서버 연결에 실패했습니다.',
        )
      })

    return () => {
      active = false
    }
  }, [ensure])

  // ==========================================================
  // 프롤로그 장면
  // ==========================================================

  const intro = beat < OPENING.length

  const openingScene = intro
    ? OPENING[beat].scene
    : null

  const backgroundScene = intro
    ? openingScene
    : place?.key ?? null

  // ==========================================================
  // 다음 스토리 장면
  // ==========================================================

  const next = () => {
    const nextBeat = Math.min(
      beat + 1,
      OPENING.length,
    )

    setBeat(nextBeat)
    saveStoryBeat(nextBeat)
  }

  // ==========================================================
  // 프롤로그 건너뛰기
  // ==========================================================

  const skipIntro = () => {
    setBeat(OPENING.length)
    saveStoryBeat(OPENING.length)
  }

  // ==========================================================
  // 현장 방문
  // ==========================================================

  const visit = (selectedPlace: Place) => {
    setPlace(selectedPlace)

    setSeen((current) => {
      if (current.includes(selectedPlace.key)) {
        return current
      }

      const updated = [
        ...current,
        selectedPlace.key,
      ]

      saveSeenPlaces(updated)

      return updated
    })
  }

  // ==========================================================
  // Issue #59: 인물 대화 시작 전 도움말 확인
  // ==========================================================

  const startDialogue = () => {
    if (!sessionReady || !sessionId) return

    // 이번 세션에서 이미 도움말을 확인했다면 바로 이동합니다.
    if (hasSeenHelp(sessionId)) {
      navigate(`/chat/${first}`)
      return
    }

    // 처음 시작하는 세션이면 도움말을 표시합니다.
    setHelpOpen(true)
  }

  // ==========================================================
  // 도움말 확인 및 NPC 대화 시작
  // ==========================================================

  const completeTutorial = () => {
    if (!sessionId) {
      setHelpOpen(false)
      return
    }

    // 실제로 도움말을 닫는 시점에 확인 완료 처리
    saveHelpSeen(sessionId)

    setHelpOpen(false)

    // 첫 NPC 대화 화면으로 이동
    navigate(`/chat/${first}`)
  }

  // ==========================================================
  // 서버 세션 로딩 화면
  // ==========================================================

  if (!sessionReady) {
    return (
      <div className={styles.page}>
        <TopNav />

        <main className={styles.main}>
          <section
            className={styles.box}
            role={sessionError ? 'alert' : 'status'}
          >
            <p className={styles.line}>
              {sessionError ??
                '사건 기록을 불러오는 중입니다.'}
            </p>

            {sessionError && (
              <button
                type="button"
                className={styles.go}
                onClick={() => navigate('/')}
              >
                메인 화면으로
              </button>
            )}
          </section>
        </main>
      </div>
    )
  }

  // ==========================================================
  // 화면 렌더링
  // ==========================================================

  return (
    <div className={styles.page}>
      {/* ======================================================
          배경 화면
          ====================================================== */}

      <AnimatePresence mode="sync">
        <motion.div
          key={backgroundScene ?? 'outside'}
          className={styles.bg}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.8 }}
        >
          {backgroundScene ? (
            <PlaceScene place={backgroundScene} />
          ) : (
            <PosterScene />
          )}
        </motion.div>
      </AnimatePresence>

      <div className={styles.dim} />

      {/* 상단 내비게이션 */}
      <TopNav />

      {/* ======================================================
          계단 장면 사건 현장 사진
          ====================================================== */}

      <AnimatePresence>
        {backgroundScene === 'stairs' &&
          !photoMissing && (
            <motion.figure
              key="scene-photo"
              className={styles.scenePhoto}
              initial={{
                opacity: 0,
                y: 10,
                rotate: 4,
              }}
              animate={{
                opacity: 1,
                y: 0,
                rotate: 2,
              }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
            >
              <img
                src={`${import.meta.env.BASE_URL}assets/scene/victim_stairs.webp`}
                alt="사건 현장 사진 — 내부 계단 아래"
                draggable={false}
                onError={() => setPhotoMissing(true)}
              />

              <figcaption>
                사건 현장
              </figcaption>
            </motion.figure>
          )}
      </AnimatePresence>

      {/* ======================================================
          메인 콘텐츠
          ====================================================== */}

      <main className={styles.main}>
        <AnimatePresence mode="wait">
          {intro ? (
            // ==================================================
            // 프롤로그
            // ==================================================

            <motion.section
              key={`story-${beat}`}
              className={styles.box}
              initial={{
                opacity: 0,
                y: 16,
              }}
              animate={{
                opacity: 1,
                y: 0,
              }}
              exit={{
                opacity: 0,
                y: -8,
              }}
              transition={{ duration: 0.45 }}
              aria-label="사건 프롤로그"
            >
              <VisualNovelDialogue
                key={`opening-novel-${beat}`}
                chapter={OPENING[beat].chapter}
                lines={[OPENING[beat].text]}
                progress={`${String(beat + 1).padStart(2, '0')} / ${String(OPENING.length).padStart(2, '0')}`}
                onNext={next}
                onSkip={skipIntro}
                nextLabel={
                  beat === OPENING.length - 1
                    ? '현장 조사 시작'
                    : '다음 장면'
                }
              />
            </motion.section>
          ) : (
            // ==================================================
            // 현장 탐색
            // ==================================================

            <motion.section
              key="choose"
              className={styles.box}
              initial={{
                opacity: 0,
                y: 12,
              }}
              animate={{
                opacity: 1,
                y: 0,
              }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
            >
              <p className={styles.place}>
                어디를 살펴볼까?

                <span className={styles.count}>
                  살펴본 곳 {seen.length} / {PLACES.length}
                </span>
              </p>

              <div className={styles.places}>
                {PLACES.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={[
                      styles.pl,
                      place?.key === item.key
                        ? styles.cur
                        : '',
                    ].join(' ')}
                    onClick={() => visit(item)}
                  >
                    {item.name}

                    {seen.includes(item.key) ? (
                      <small> ✓</small>
                    ) : (
                      <i
                        className={styles.new}
                        aria-label="아직 살펴보지 않음"
                      />
                    )}
                  </button>
                ))}
              </div>

              <p
                className={styles.obs}
                aria-live="polite"
              >
                {place
                  ? place.text
                  : '장소를 선택하면 관찰한 내용이 표시됩니다.'}
              </p>

              <div className={styles.actions}>
                {seen.length < PLACES.length && (
                  <span className={styles.left}>
                    아직 살펴보지 않은 곳이{' '}
                    {PLACES.length - seen.length}곳 남아 있습니다.
                  </span>
                )}

                <button
                  type="button"
                  className={styles.go}
                  disabled={!sessionId}
                  onClick={startDialogue}
                >
                  관계자에게 이야기를 듣는다
                </button>
              </div>
            </motion.section>
          )}
        </AnimatePresence>
      </main>

      {/* ======================================================
          Issue #59 — 최초 NPC 대화 전 도움말
          ====================================================== */}

      <GameHelp
        open={helpOpen}
        onClose={completeTutorial}
      />
    </div>
  )
}
