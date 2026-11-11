
import { useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  AnimatePresence,
  motion,
  useReducedMotion,
} from 'framer-motion'

import CharacterPortrait from '../../components/CharacterPortrait'
import { npcName } from '../../data/characters'
import {
  useGameStore,
  type FinalRecord,
} from '../../store/gameStore'
import {
  NOTE_SECTIONS,
  useNoteStore,
} from '../../store/noteStore'
import type { EvidenceDetail } from '../../api/types'
import styles from './Final.module.css'

// ============================================================
// Issue #59 — Cinematic Ending
// ============================================================

const ENDING_PROGRESS_KEY = 'serin-ending-progress-v1'

const RESULT_LABEL = {
  FULL: '사건 해결',
  ESTIMATED: '추정 성립',
  WRONG: '지목 실패',
  NOT_ENOUGH_EVIDENCE: '단서 부족',
} as const

interface EndingScene {
  chapter: string
  title: string
  lines: string[]
}

// ============================================================
// 진행 상태 저장
// ============================================================

function loadEndingStep(
  sessionId: string,
  max: number,
): number {
  if (!sessionId) return 0

  try {
    const raw = localStorage.getItem(ENDING_PROGRESS_KEY)
    if (!raw) return 0

    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return 0

    const value = parsed as {
      sessionId?: unknown
      step?: unknown
    }

    if (
      value.sessionId !== sessionId ||
      typeof value.step !== 'number' ||
      !Number.isFinite(value.step)
    ) {
      return 0
    }

    return Math.max(
      0,
      Math.min(Math.trunc(value.step), max),
    )
  } catch {
    return 0
  }
}

function saveEndingStep(
  sessionId: string,
  step: number,
): void {
  if (!sessionId) return

  try {
    localStorage.setItem(
      ENDING_PROGRESS_KEY,
      JSON.stringify({ sessionId, step }),
    )
  } catch {
    // 저장 실패 시에도 화면 진행은 유지합니다.
  }
}

// ============================================================
// 엔딩 스토리 구성
// ============================================================

function buildEndingScenes(
  final: FinalRecord,
  evidence: Record<string, EvidenceDetail>,
): EndingScene[] {
  const { response, suspectId, evidenceIds } = final

  const suspectName = suspectId
    ? npcName(suspectId)
    : '지목 기록이 남아 있지 않은 인물'

  // 실제 플레이어가 지목할 때 기록한 증거만 사용합니다.
  const evidenceNames = evidenceIds.map(
    (id) =>
      final.evidenceTitles?.[id] ??
      evidence[id]?.title ??
      id,
  )

  const firstEvidence = evidenceNames.slice(0, 3)
  const remainingEvidence = evidenceNames.slice(3)

  const scenes: EndingScene[] = [
    {
      chapter: 'FINAL CHAPTER · 마지막 지목',
      title: '그 이름을 입 밖으로 꺼냈다',
      lines: [
        '긴 조사가 끝을 향해 가고 있었다.',
        '서로 다른 진술, 설명되지 않은 흔적, 그리고 수차례 되짚어 본 그날 밤의 기록.',
        `당신이 마지막으로 지목한 사람은 ${suspectName}.`,
        '이제 남은 것은 그 선택에 대한 대답이었다.',
      ],
    },
    {
      chapter: 'RECORD 01 · 남겨진 것들',
      title: '기록은 사라지지 않는다',
      lines: [
        '처음에는 모든 것이 서로 관계없는 조각처럼 보였다.',
        '그러나 조사를 이어갈수록 작은 단서들이 하나씩 기록에 남았다.',
        firstEvidence.length > 0
          ? firstEvidence.join(' · ')
          : '마지막 지목에 제출한 증거 목록은 기록되지 않았다.',
        '각각의 기록은 그날 밤을 다시 바라보게 만들었다.',
      ],
    },
    {
      chapter: 'RECORD 02 · 서로 다른 진술',
      title: '같은 밤, 다른 이야기',
      lines: [
        '같은 장소에 있었던 사람들도 서로 다른 말을 했다.',
        '어떤 진술은 기록과 맞아떨어졌고, 어떤 진술은 새로운 질문을 남겼다.',
        remainingEvidence.length > 0
          ? `당신이 함께 검토한 나머지 기록: ${remainingEvidence.join(' · ')}.`
          : '당신은 확보한 기록과 관계자들의 진술을 다시 떠올렸다.',
        '이제 그 이야기들을 하나의 결론으로 연결해야 했다.',
      ],
    },
    {
      chapter: 'RECORD 03 · 침묵',
      title: '마지막 질문',
      lines: [
        '당신의 지목이 끝나자 잠시 침묵이 흘렀다.',
        '오래된 학교의 복도에는 아무런 대답도 돌아오지 않았다.',
        '결정적인 것은 가장 큰 목소리가 아니었다.',
        '끝까지 확인할 수 있었던 사실들이었다.',
      ],
    },
  ]

  // 실제 판정은 서버가 제공한 결과만 사용합니다.
  if (response.result === 'FULL') {
    scenes.push({
      chapter: 'VERDICT · 사건 해결',
      title: '하나의 결론에 도달했다',
      lines: [
        '당신의 지목은 확인된 사건 기록과 일치했다.',
        '오래도록 엇갈렸던 이야기들은 마침내 하나의 결론으로 이어졌다.',
        '이제 사건의 진실을 기록할 차례였다.',
      ],
    })

    // 성공 판정 + 서버가 제공한 진실만 공개합니다.
    if (response.truth) {
      scenes.push({
        chapter: 'THE TRUTH · 사건의 진실',
        title: '그날 밤에 일어난 일',
        lines: [
          `범인으로 확인된 인물은 ${npcName(response.truth.perpetratorId)}.`,
          `범행 동기: ${response.truth.motive}`,
          `사망 원인: ${response.truth.causeOfDeath}`,
          `범행 수법: ${response.truth.crimeMethod}`,
        ],
      })
    } else {
      scenes.push({
        chapter: 'THE TRUTH · 최종 기록',
        title: '확인된 결론',
        lines: [
          '사건 해결은 확인되었다.',
          '세부 사건 기록은 서버에서 제공된 최종 결과를 기준으로 확인할 수 있다.',
        ],
      })
    }

    scenes.push({
      chapter: 'EPILOGUE · 마지막 기록',
      title: '끝나지 않을 것 같던 밤',
      lines: [
        '사건의 진실에 도달했다고 해서, 그날의 시간이 되돌아오는 것은 아니다.',
        '누군가의 마지막 순간은 이제 하나의 사건 기록으로 남게 되었다.',
        response.endingKind === 'DEEP'
          ? '당신은 표면에 드러난 사실을 넘어, 사건의 더 깊은 기록까지 확인했다.'
          : '당신이 확인한 사실들은 더 이상 추측만으로 남아 있지 않았다.',
        '사건 파일을 덮기 전, 마지막 기록을 확인하자.',
      ],
    })
  } else if (response.result === 'ESTIMATED') {
    scenes.push(
      {
        chapter: 'VERDICT · 추정 성립',
        title: '가능성은 남아 있었다',
        lines: [
          '당신의 추리는 하나의 가능성을 보여주었다.',
          '그러나 모든 의문에 답할 만큼 충분한 결론에 이르지는 못했다.',
          '확인된 사실과 아직 확인되지 않은 가설은 구분해야 했다.',
        ],
      },
      {
        chapter: 'EPILOGUE · 남겨진 질문',
        title: '확인되지 않은 진실',
        lines: [
          '기록은 남아 있지만 모든 문장이 해답이 되는 것은 아니었다.',
          '당신의 추리는 사건의 일부를 설명했으나, 남겨진 질문까지 지우지는 못했다.',
          '이번 조사의 마지막 기록을 확인하자.',
        ],
      },
    )
  } else {
    scenes.push(
      {
        chapter: 'VERDICT · 지목 실패',
        title: '대답은 돌아오지 않았다',
        lines: [
          '당신이 내린 결론은 사건을 해결하기에 충분하지 않았다.',
          '기록된 사실과 마지막 지목 사이에는 여전히 설명되지 않은 부분이 남아 있었다.',
          '그날 밤의 진실은 이번 조사에서 완전히 밝혀지지 않았다.',
        ],
      },
      {
        chapter: 'EPILOGUE · 미해결 기록',
        title: '기록은 이곳에 남는다',
        lines: [
          '끝까지 답하지 못한 질문들이 있었다.',
          '하지만 당신이 확인한 기록이 사라지는 것은 아니다.',
          '사건은 미해결 기록으로 남았고, 마지막 조사 결과가 정리되었다.',
        ],
      },
    )
  }

  return scenes
}

// ============================================================
// Final
// ============================================================

export default function Final() {
  const navigate = useNavigate()
  const reduceMotion = useReducedMotion()

  const final = useGameStore((s) => s.final)
  const session = useGameStore((s) => s.session)
  const starting = useGameStore((s) => s.starting)
  const ensure = useGameStore((s) => s.ensureSession)
  const recoverEnding = useGameStore((s) => s.recoverEnding)
  const endingError = useGameStore((s) => s.endingError)
  const evidence = useGameStore((s) => s.evidence)
  const reset = useGameStore((s) => s.resetGame)

  const notes = useNoteStore((s) => s.notes)

  const [loadError, setLoadError] = useState<string | null>(null)
  const [step, setStep] = useState(0)
  const [restoredSession, setRestoredSession] = useState<string | null>(null)

  useEffect(() => {
    void ensure().catch((error: unknown) => {
      setLoadError(
        error instanceof Error
          ? error.message
          : '세션 조회에 실패했습니다.',
      )
    })
  }, [ensure])

  const scenes = useMemo(
    () => (final ? buildEndingScenes(final, evidence) : []),
    [final, evidence],
  )

  const sessionId =
    final?.sessionId ?? session?.sessionId ?? ''

  // 같은 세션은 엔딩 진행 위치를 복원합니다.
  useEffect(() => {
    if (!final) return

    setStep(loadEndingStep(sessionId, scenes.length))
    setRestoredSession(sessionId)
  }, [final?.sessionId, sessionId, scenes.length])

  const updateStep = (value: number) => {
    const next = Math.max(
      0,
      Math.min(value, scenes.length),
    )

    setStep(next)
    saveEndingStep(sessionId, next)
  }

  const replayStory = () => {
    updateStep(0)
  }

  const goHome = () => {
    try {
      localStorage.removeItem(ENDING_PROGRESS_KEY)
    } catch {
      // 초기화는 계속 진행합니다.
    }

    reset()
    navigate('/')
  }

  // ==========================================================
  // 서버 엔딩 복구
  // ==========================================================

  if (!final) {
    if (session?.phase === 'FINISHED') {
      return (
        <div className={styles.page}>
          <main className={styles.wrap}>
            <p className={styles.kicker}>
              CASE 001 · 사건 종료
            </p>
            <h1 className="serif">엔딩 확인</h1>
            <p className={styles.ending}>
              {endingError ??
                '서버에서 엔딩 정보를 불러오는 중입니다.'}
            </p>
            <button
              type="button"
              className="btn"
              onClick={() => void recoverEnding(session)}
            >
              엔딩 다시 불러오기
            </button>
          </main>
        </div>
      )
    }

    if (!session || starting || loadError) {
      return (
        <div className={styles.page}>
          <main className={styles.wrap}>
            <p className={styles.ending}>
              {loadError ??
                '게임 기록을 확인하는 중입니다.'}
            </p>

            {loadError && (
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setLoadError(null)

                  void ensure().catch((error: unknown) => {
                    setLoadError(
                      error instanceof Error
                        ? error.message
                        : '세션 조회 실패',
                    )
                  })
                }}
              >
                다시 시도
              </button>
            )}
          </main>
        </div>
      )
    }

    return <Navigate to="/accuse" replace />
  }

  // 진행 위치 복원 전 결과를 표시하지 않습니다.
  if (restoredSession !== sessionId) {
    return (
      <div className={styles.page}>
        <main className={styles.wrap}>
          <p className={styles.ending}>
            마지막 기록을 준비하고 있습니다.
          </p>
        </main>
      </div>
    )
  }

  const { response, suspectId, evidenceIds } = final
  const finishedStory = step >= scenes.length

  const ending = response.ending ?? {
    title:
      response.result === 'FULL'
        ? '사건 종결'
        : '진실은 어둠 속에 남았다',
    text:
      response.result === 'FULL' ||
      response.result === 'ESTIMATED'
        ? '수사가 마무리되었습니다.'
        : '모든 지목 기회를 사용했습니다. 이번 수사에서는 사건의 진실에 닿지 못했습니다.',
  }

  // ==========================================================
  // 엔딩 스토리
  // ==========================================================

  if (!finishedStory) {
    const scene = scenes[step]

    return (
      <div className={`${styles.page} ${styles.cinematicPage}`}>
        <div className={styles.cinematicBackdrop} aria-hidden="true" />

        <main className={styles.cinematicMain}>
          <AnimatePresence mode="wait">
            <motion.section
              key={`ending-scene-${step}`}
              className={styles.cinematicScene}
              initial={
                reduceMotion
                  ? false
                  : { opacity: 0, y: 18 }
              }
              animate={{ opacity: 1, y: 0 }}
              exit={
                reduceMotion
                  ? { opacity: 1 }
                  : { opacity: 0, y: -12 }
              }
              transition={{
                duration: reduceMotion ? 0 : 0.55,
              }}
            >
              <p className={styles.sceneChapter}>
                {scene.chapter}
              </p>

              <h1 className={`serif ${styles.sceneTitle}`}>
                {scene.title}
              </h1>

              <div className={styles.sceneLines}>
                {scene.lines.map((line, index) => (
                  <motion.p
                    key={`${step}-${index}`}
                    initial={
                      reduceMotion
                        ? false
                        : { opacity: 0, y: 8 }
                    }
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      delay: reduceMotion ? 0 : 0.25 + index * 0.18,
                      duration: reduceMotion ? 0 : 0.55,
                    }}
                  >
                    {line}
                  </motion.p>
                ))}
              </div>

              <div className={styles.sceneControls}>
                <span className={styles.sceneProgress}>
                  {String(step + 1).padStart(2, '0')}
                  {' / '}
                  {String(scenes.length).padStart(2, '0')}
                </span>

                <button
                  type="button"
                  className={styles.sceneSkip}
                  onClick={() => updateStep(scenes.length)}
                >
                  스토리 건너뛰기
                </button>

                <button
                  type="button"
                  className={styles.sceneNext}
                  onClick={() => updateStep(step + 1)}
                >
                  {step === scenes.length - 1
                    ? '최종 기록 확인'
                    : '다음 장면 →'}
                </button>
              </div>
            </motion.section>
          </AnimatePresence>
        </main>
      </div>
    )
  }

  // ==========================================================
  // 기존 최종 결과 화면
  // ==========================================================

  return (
    <div
      className={[
        styles.page,
        styles[response.result] ?? '',
        response.endingKind === 'DEEP' ? styles.DEEP : '',
      ].join(' ')}
    >
      <motion.main
        className={styles.wrap}
        initial={reduceMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: reduceMotion ? 0 : 0.8 }}
      >
        <p className={styles.kicker}>
          CASE 001 · 마지막 기록: 졸업하지 못한 밤
        </p>

        <h1 className="serif">{ending.title}</h1>

        <p className={styles.verdict}>
          판정 · {RESULT_LABEL[response.result]}

          {response.endingKind === 'DEEP' && (
            <span className={styles.deep}>심화 엔딩</span>
          )}
        </p>

        <p className={styles.ending}>{ending.text}</p>

        {endingError && session?.phase === 'FINISHED' && (
          <div role="alert">
            <p>{endingError}</p>

            <button
              type="button"
              className="btn"
              onClick={() => void recoverEnding(session)}
            >
              엔딩 상세 다시 불러오기
            </button>
          </div>
        )}

        {/* 성공 판정 + 서버 승인 데이터일 때만 진실 공개 */}
        {response.result === 'FULL' && response.truth && (
          <section
            className={styles.truth}
            aria-label="사건의 진실"
          >
            <h2 className="serif">사건의 진실</h2>

            <dl>
              <div>
                <dt>범인</dt>
                <dd>
                  {npcName(response.truth.perpetratorId)}
                </dd>
              </div>

              <div>
                <dt>동기</dt>
                <dd>{response.truth.motive}</dd>
              </div>

              <div>
                <dt>사망 원인</dt>
                <dd>{response.truth.causeOfDeath}</dd>
              </div>

              <div>
                <dt>범행 수법</dt>
                <dd>{response.truth.crimeMethod}</dd>
              </div>
            </dl>
          </section>
        )}

        <section className={styles.cols}>
          <div className={styles.accused}>
            <h2>나의 지목</h2>

            {suspectId && (
              <CharacterPortrait
                id={suspectId}
                alt=""
                className={styles.face}
              />
            )}

            <b className="serif">
              {suspectId
                ? npcName(suspectId)
                : '지목 기록을 복구하지 못했습니다.'}
            </b>

            <ul>
              {evidenceIds.map((id) => (
                <li key={id}>
                  <span>{id}</span>{' '}
                  {final.evidenceTitles?.[id] ??
                    evidence[id]?.title ??
                    ''}
                </li>
              ))}
            </ul>
          </div>

          <div className={styles.record}>
            <h2>나의 최종 추리 기록</h2>

            <p className={styles.sub}>
              직접 쓴 노트가 그대로 표시됩니다.
              판정과는 관계없습니다.
            </p>

            {NOTE_SECTIONS.map((section, index) => (
              <article key={section.key}>
                <h3>
                  <b>{index + 1}</b> {section.title}
                </h3>

                <p>
                  {notes[section.key].trim() ||
                    '작성하지 않았습니다.'}
                </p>
              </article>
            ))}
          </div>
        </section>

        <div className={styles.finalActions}>
          <button
            type="button"
            className="btn"
            onClick={replayStory}
          >
            엔딩 스토리 다시 보기
          </button>

          <button
            type="button"
            className="btn"
            onClick={goHome}
          >
            처음으로
          </button>
        </div>
      </motion.main>
    </div>
  )
}
