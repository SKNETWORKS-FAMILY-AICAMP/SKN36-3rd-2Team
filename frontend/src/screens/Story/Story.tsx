import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'

import TopNav from '../../components/TopNav'
import PosterScene from '../../components/PosterScene'
import PlaceScene from '../../components/PlaceScene'
import VisualNovelDialogue from '../../components/VisualNovelDialogue'
import { api } from '../../api/client'
import { useGameStore } from '../../store/gameStore'
import styles from './Story.module.css'

// Issue #203 — 기존 프롤로그 연출 유지, 조사 화면 분리
const STORY_KEY = 'serin-story-beat-v2'

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

export default function Story() {
  const navigate = useNavigate()
  const session = useGameStore((state) => state.session)
  const ensure = useGameStore((state) => state.ensureSession)
  const refresh = useGameStore((state) => state.refresh)
  const [beat, setBeat] = useState(loadStoryBeat)
  const [sessionReady, setSessionReady] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [photoMissing, setPhotoMissing] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [completeError, setCompleteError] = useState<string | null>(null)
  const completingRef = useRef(false)

  useEffect(() => {
    let active = true
    void ensure()
      .then(() => {
        if (!active) return
        const current = useGameStore.getState().session
        if (!current) throw new Error('게임 세션을 불러오지 못했습니다.')

        // 이미 프롤로그를 완료한 서버 세션은 다시 완료하지 않습니다.
        if (current.phase === 'INVESTIGATION') {
          saveStoryBeat(OPENING.length)
          navigate('/play', { replace: true })
          return
        }
        if (current.phase === 'FINISHED') {
          navigate('/final', { replace: true })
          return
        }
        if (current.phase === 'ACCUSATION') {
          navigate('/accuse', { replace: true })
          return
        }

        setBeat(loadStoryBeat())
        setSessionError(null)
        setSessionReady(true)
      })
      .catch((error: unknown) => {
        if (!active) return
        setSessionReady(false)
        setSessionError(error instanceof Error ? error.message : '서버 연결에 실패했습니다.')
      })
    return () => { active = false }
  }, [ensure, navigate])

  // 마지막 장면과 건너뛰기 모두 동일한 서버 완료 절차를 사용합니다.
  const finishPrologue = async () => {
    if (!sessionReady || !session || completingRef.current) return
    completingRef.current = true
    setCompleting(true)
    setCompleteError(null)
    try {
      await api.completePrologue(session.sessionId)
      await refresh()
      const current = useGameStore.getState().session
      if (current?.sessionId !== session.sessionId || current.phase !== 'INVESTIGATION') {
        throw new Error('조사 단계 전환을 확인하지 못했습니다.')
      }
      saveStoryBeat(OPENING.length)
      navigate('/play', { replace: true })
    } catch (error: unknown) {
      setCompleteError(error instanceof Error ? error.message : '조사 시작에 실패했습니다.')
    } finally {
      completingRef.current = false
      setCompleting(false)
    }
  }

  const next = () => {
    if (completingRef.current) return
    if (beat >= OPENING.length - 1) {
      void finishPrologue()
      return
    }
    const nextBeat = beat + 1
    setBeat(nextBeat)
    saveStoryBeat(nextBeat)
  }

  const skipIntro = () => { void finishPrologue() }
  const intro = beat < OPENING.length
  const backgroundScene = intro ? OPENING[beat].scene : null

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

      <main className={styles.main}>
        <AnimatePresence mode="wait">
          <motion.section
            key={intro ? `story-${beat}` : 'complete'}
            className={styles.box}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45 }}
            aria-label="사건 프롤로그"
            aria-busy={completing}
          >
            {intro ? (
              <VisualNovelDialogue
                key={`opening-novel-${beat}`}
                chapter={OPENING[beat].chapter}
                lines={[OPENING[beat].text]}
                progress={`${String(beat + 1).padStart(2, '0')} / ${String(OPENING.length).padStart(2, '0')}`}
                onNext={next}
                onSkip={skipIntro}
                nextLabel={beat === OPENING.length - 1 ? '현장 조사 시작' : '다음 장면'}
              />
            ) : (
              <button type="button" className={styles.go} disabled={completing} onClick={skipIntro}>
                현장 조사 시작
              </button>
            )}
            {completing && <p className={styles.line} role="status">조사 단계로 전환하는 중입니다.</p>}
            {completeError && (
              <div role="alert">
                <p className={styles.line}>{completeError}</p>
                <button type="button" className={styles.go} disabled={completing} onClick={skipIntro}>
                  다시 시도
                </button>
              </div>
            )}
          </motion.section>
        </AnimatePresence>
      </main>
    </div>
  )
}
