
import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { FileSearch, Lightbulb, NotebookPen, Pin, Send, X } from 'lucide-react'

import Objective from '../../components/Objective'
import ConsentModal from '../../components/ConsentModal'
import { EvidenceCompare } from '../Evidence/EvidenceParts'
import type { EmbedProps } from '../embed'
import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import CharacterPortrait from '../../components/CharacterPortrait'
import TypingText from '../../components/TypingText'

import { MEETING_BG, NPC_PUBLIC } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import { MAX_DRAFT, useChatStore } from '../../store/chatStore'
import { useNoteStore } from '../../store/noteStore'
import { api } from '../../api/client'
import { ApiHttpError, SERVER_PRESENT_MAX } from '../../api/httpApi'

import type { AvailableEvidence, Message } from '../../api/types'
import styles from './Chat.module.css'

const EMPTY: never[] = []
// 타이핑 효과를 이미 보여 준 답변 (다른 인물에게 갔다 돌아와도 다시 재생하지 않음)
const typed = new WeakSet<Message>()

// Issue #59: NPC 대화 입력 최대 길이
const MAX_MESSAGE_LENGTH = 200
const CONSENT_DECLINED_KEY = 'serin-consent-declined'

export default function Chat({ embedded = false, npcId: npcProp, onNpcSelect }: EmbedProps & { npcId?: string } = {}) {
  const params = useParams()
  const npcId = npcProp ?? params.npcId
  const navigate = useNavigate()
  const { search } = useLocation()
  // 인물 이동: 통합 화면이면 Play에 맡기고, 독립 화면이면 주소를 바꾼다
  const selectNpc = (id: string) => (onNpcSelect ? onNpcSelect(id) : navigate({ pathname: `/chat/${id}`, search }))

  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const evidence = useGameStore((s) => s.evidence)
  const loadEvidence = useGameStore((s) => s.loadEvidence)

  const messages = useChatStore(
    (s) => (npcId ? s.messages[npcId] ?? EMPTY : EMPTY),
  )

  // 가장 최근 인물 대사(통합 화면에서 강조)
  const lastNpcIdx = embedded ? messages.map((m) => m.role).lastIndexOf('npc') : -1
  const allMessages = useChatStore((s) => s.messages)
  const typing = useChatStore((s) => s.typing)
  const isLoaded = useChatStore(
    (s) => (npcId ? !!s.loaded[npcId] : true),
  )
  const error = useChatStore((s) => s.error)
  const load = useChatStore((s) => s.load)
  const retry = useChatStore((s) => s.retry)
  const canRetry = useChatStore((s) => s.canRetry)
  const send = useChatStore((s) => s.send)
  // 진술 저장: 메시지 id는 새로고침하면 바뀌므로 인물+내용으로 구분한다
  const statements = useNoteStore((s) => s.statements)
  const toggleStatement = useNoteStore((s) => s.toggleStatement)
  const savedIds = useMemo(() => new Set(statements.map((s) => s.id)), [statements])
  const present = useChatStore((s) => s.present)

  const [text, setText] = useState('')
  const [pickOpen, setPickOpen] = useState(false)
  // 고르는 창 안 「나란히 보기」(증거 2개를 좌우로)
  const [sideBySide, setSideBySide] = useState(false)
  const closePick = () => { setPickOpen(false); setSideBySide(false) }
  // 제시할 증거(칩, 최대 2개): 입력창 위에 표시되고, 다음 전송 때 질문과 함께 보낸다
  const draft = useChatStore((s) => s.draft)
  const { addDraft, removeDraft, clearDraft } = useChatStore.getState()
  const overServer = draft.length > SERVER_PRESENT_MAX
  // 열람 동의: 서버가 동의 가능하다고 하고, 아직 동의·거절하지 않았을 때만 띄운다. 거절은 이번 게임(세션) 동안 기억한다
  const refresh = useGameStore((s) => s.refresh)
  const [declinedSid, setDeclinedSid] = useState<string | null>(() => {
    try { return localStorage.getItem(CONSENT_DECLINED_KEY) } catch { return null }
  })
  const [consentBusy, setConsentBusy] = useState(false)
  const [consentError, setConsentError] = useState<string | null>(null)
  const consentOpen = !!session?.consentAvailable && !session.consentGranted && declinedSid !== session.sessionId
  const declineConsent = () => {
    if (!session) return
    try { localStorage.setItem(CONSENT_DECLINED_KEY, session.sessionId) } catch { /* ignore */ }
    setDeclinedSid(session.sessionId)
  }
  const agreeConsent = async () => {
    if (!session || consentBusy) return
    setConsentBusy(true)
    setConsentError(null)
    try {
      await api.giveConsent(session.sessionId)
      await refresh()
    } catch (error) {
      if (error instanceof ApiHttpError && error.status === 409) {
        await refresh().catch(() => undefined)
        setConsentError('지금은 동의할 수 없는 상태입니다. 게임 상태를 다시 불러왔습니다.')
      } else {
        setConsentError('동의를 저장하지 못했습니다. 잠시 후 다시 눌러 주세요.')
      }
    } finally {
      setConsentBusy(false)
    }
  }
  // 힌트 1단계: 서버가 준 문장을 입력창 위에 보여 준다
  const [hint, setHint] = useState<{ text: string; error?: boolean } | null>(null)
  const [hintBusy, setHintBusy] = useState(false)
  const askHint = async () => {
    if (!session || hintBusy) return
    setHintBusy(true)
    const fail = { text: '지금은 힌트를 볼 수 없습니다. 조사 중일 때 다시 눌러 보세요.', error: true }
    try {
      const text = await api.getHint(session.sessionId)
      setHint(text ? { text } : fail)
    } catch {
      setHint(fail)
    } finally {
      setHintBusy(false)
    }
  }
  const [available, setAvailable] = useState<AvailableEvidence[]>([])
  const [collecting, setCollecting] = useState<string | null>(null)
  const collectingRef = useRef(false)
  const [collectError, setCollectError] = useState<string | null>(null)

  const listRef = useRef<HTMLDivElement>(null)

  // ============================================================
  // 세션 및 대화 기록 로딩
  // ============================================================

  useEffect(() => {
    void ensure()
  }, [ensure])

  const sid = session?.sessionId

  useEffect(() => {
    if (sid && npcId) {
      void load(npcId)
    }
  }, [sid, npcId, load])

  // 인물을 바꾸면 골라 둔 증거를 지운다 (다른 인물에게 잘못 제시되지 않게)
  const pickedFor = useRef(npcId)
  useEffect(() => {
    // 처음 인물이 정해질 때(화면 진입)는 비우지 않는다: 증거 화면 「이 증거로 질문」으로 붙인 칩 유지
    if (pickedFor.current && pickedFor.current !== npcId) clearDraft()
    pickedFor.current = npcId
  }, [npcId, clearDraft])

  // 다른 인물과의 대화 여부를 미리 불러옵니다.
  useEffect(() => {
    if (sid && npcId && session?.unlockedNpcs.includes(npcId)) {
      try { localStorage.setItem('serin-last-room', JSON.stringify({ sid, npcId })) } catch { /* optional persistence */ }
    }
  }, [sid, npcId, session])

  function lastRoom() {
    try {
      const room = JSON.parse(localStorage.getItem('serin-last-room') ?? 'null')
      if (room?.sid === sid && unlocked.includes(room.npcId)) return room.npcId
    } catch { /* use first available room */ }
    return unlocked[0] ?? 'C01'
  }

  const unlockedKey = session?.unlockedNpcs.join()

  useEffect(() => {
    if (!sid) return

    session?.unlockedNpcs.forEach((id) => {
      if (id !== npcId) {
        void load(id)
      }
    })

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, unlockedKey])

  // 새 메시지가 생기면 스크롤을 아래로 이동합니다.
  useEffect(() => {
    const element = listRef.current

    if (element) {
      element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [messages.length, typing])

  // ============================================================
  // 확보 가능한 증거 조회
  // ============================================================

  const activeRevision = session?.revision
  const activeNpcId = session?.activeCharacterId

  useEffect(() => {
    if (
      !sid ||
      !npcId ||
      session?.phase !== 'INVESTIGATION' ||
      activeNpcId !== npcId
    ) {
      setAvailable([])
      return
    }

    let active = true

    api.getAvailableEvidence(sid)
      .then((items) => {
        if (active) {
          setAvailable(items)
        }
      })
      .catch(() => {
        if (active) {
          setAvailable([])
        }
      })

    return () => {
      active = false
    }
  }, [
    sid,
    npcId,
    activeRevision,
    activeNpcId,
    session?.phase,
  ])

  // ============================================================
  // 증거 확보
  // ============================================================

  const collect = async (evidenceId: string) => {
    if (!sid || typing !== null || collectingRef.current) {
      return
    }

    collectingRef.current = true
    setCollecting(evidenceId)
    setCollectError(null)

    try {
      const events = await api.collectEvidence(
        sid,
        evidenceId,
      )

      await useGameStore.getState().handleEvents(events)

      setAvailable(
        await api.getAvailableEvidence(sid),
      )
    } catch (error) {
      // 중복 요청으로 증거가 두 번 처리되지 않도록 합니다.
      try {
        await useGameStore.getState().refresh()
      } catch {
        // 기존 상태 유지
      }

      setCollectError(
        error instanceof Error
          ? error.message
          : '증거 확보에 실패했습니다.',
      )
    } finally {
      collectingRef.current = false
      setCollecting(null)
    }
  }

  // ============================================================
  // 현재 NPC 및 대화 상태
  // ============================================================

  const unlocked = session?.unlockedNpcs ?? []

  const npc = useMemo(
    () => NPC_PUBLIC.find((n) => n.id === npcId),
    [npcId],
  )

  // 통합 화면에서 인물이 없거나 아직 못 만나는 인물이면, 주소 이동 대신 마지막(또는 첫) 인물을 Play에 알린다
  const roomInvalid = !npcId || !npc || (!!session && !unlocked.includes(npcId))
  useEffect(() => {
    if (embedded && session && roomInvalid) onNpcSelect?.(lastRoom())
  }, [embedded, session, roomInvalid])

  if (embedded && roomInvalid) return <Shell embedded />

  if (!npcId) {
    return session ? (
      <Navigate
        to={{
          pathname: `/chat/${lastRoom()}`,
          search,
        }}
        replace
      />
    ) : (
      <Shell />
    )
  }

  if (!npc) {
    return (
      <Navigate
        to={{ pathname: '/chat', search }}
        replace
      />
    )
  }

  if (session && !unlocked.includes(npcId)) {
    return (
      <Navigate
        to={{ pathname: '/chat', search }}
        replace
      />
    )
  }

  const found = session?.foundEvidence ?? []
  const busy = typing !== null || collecting !== null

  // ============================================================
  // Issue #59: 입력 길이 제한 및 전송 검증
  // ============================================================

  const handleTextChange = (
    value: string,
  ) => {
    // 붙여넣기로 200자를 초과하는 경우에도 제한합니다.
    setText(value.slice(0, MAX_MESSAGE_LENGTH))
  }

  const submit = () => {
    const question = text.trim()

    if (
      (!question && !draft.length) ||
      overServer ||
      question.length > MAX_MESSAGE_LENGTH ||
      busy ||
      !session
    ) {
      return
    }

    setText('')
    if (draft.length) {
      clearDraft()
      void present(npcId, draft, draft.map((id) => evidence[id]?.title ?? id).join(' · '), question || undefined)
    } else {
      void send(npcId, question)
    }
  }

  return (
    <div className={`${styles.page} ${embedded ? styles.embedded : ''}`} style={{ backgroundImage: embedded ? `linear-gradient(rgba(10,9,8,.2), rgba(10,9,8,.5)), url(${MEETING_BG})` : `linear-gradient(rgba(10,9,8,.6), rgba(10,9,8,.8)), url(${MEETING_BG})` }}>
      {!embedded && <TopNav />}
      <ConsentModal open={consentOpen} busy={consentBusy} error={consentError} onAgree={() => void agreeConsent()} onDecline={declineConsent} />
      {!embedded && <><Toasts /><Objective /></>}

      {/* ======================================================
          인물 선택
          ====================================================== */}

      {/* data-tutorial: 튜토리얼이 가리킬 위치. 이름은 A와 맞춘다 (interview-*) */}
      {/* 통합 화면에서는 A의 왼쪽 칸이 면담 대상을 보여 주므로 숨긴다 */}
      {!embedded && <ul
        className={styles.row}
        aria-label="인물 선택"
        data-tutorial="interview-npc-list"
      >
        {/* 지금 만날 수 있는 인물만 보여 준다 (잠긴 인물은 이름·자리 모두 숨김) */}
        {NPC_PUBLIC.filter((n) => unlocked.includes(n.id)).map((n) => {
          const active = n.id === npcId

          return (
            <li key={n.id}>
              <button
                type="button"
                disabled={busy}
                className={`${styles.polaroid} ${active ? styles.current : ''}`}
                onClick={() => selectNpc(n.id)}
                aria-current={active}
                aria-label={n.name}
              >
                <span className={styles.photo}>
                  <CharacterPortrait id={n.id} alt="" />
                  {(allMessages[n.id]?.length ?? 0) > 0 && (
                    <i className={styles.talked} aria-label="이전 대화 있음" />
                  )}
                </span>

                <span className={styles.cap}>{n.name}</span>
              </button>
            </li>
          )
        })}
      </ul>}

      <main className={styles.main}>
        {/* ==================================================
            NPC 프로필
            ================================================== */}

        <aside className={styles.profile} data-tutorial="interview-profile" style={embedded ? { backgroundImage: `url(${MEETING_BG})` } : undefined}>
          <div className={styles.frame}>
            <span
              className={styles.tape}
              aria-hidden="true"
            />

            <CharacterPortrait
              id={npc.id}
              alt={`${npc.name}의 사진`}
              className={styles.portrait}
              standing
            />
          </div>

          <div className={styles.info}>
            <h2 className="serif">
              {npc.name}
            </h2>

            <p className={styles.role}>
              {npc.title}
            </p>
          </div>
        </aside>

        {/* ==================================================
            NPC 대화 화면
            ================================================== */}

        <section
          className={styles.chat}
          aria-label={`${npc.name}와의 대화`}
          data-tutorial="interview-chat"
        >
          <header className={styles.chatHead}>
            <b className="serif">
              {npc.name}
            </b>

            <span>{npc.title}</span>

            {embedded ? (
              <button type="button" className={styles.latest} onClick={() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight })}>
                최신 대사
              </button>
            ) : <em>
              {messages.length > 0
                ? `이전 대화 ${
                    messages.filter(
                      (message) =>
                        message.role === 'player',
                    ).length
                  }회`
                : '첫 대화'}
            </em>}
          </header>

          {/* 증거 확보 안내 */}

          {(available.length > 0 || collectError) && (
            <div
              className={styles.collectPanel}
              data-tutorial="interview-collect"
              role="region"
              aria-label="확보 가능한 증거"
            >
              {available.length > 0 && (
                <strong>
                  새로운 단서가 확인됐습니다
                </strong>
              )}

              {available.map((item) => (
                <button
                  type="button"
                  key={item.evidenceId}
                  className={styles.collectButton}
                  disabled={busy}
                  onClick={() =>
                    void collect(item.evidenceId)
                  }
                >
                  <FileSearch size={15} />

                  {item.evidenceId} · {item.name}
                  {' '}확보 (+{item.score}점)
                </button>
              ))}

              {collectError && (
                <span
                  className={styles.collectError}
                  role="alert"
                >
                  {collectError}
                </span>
              )}
            </div>
          )}

          {/* 대화 기록 */}

          <div
            className={styles.list}
            ref={listRef}
          >
            {messages.length === 0 &&
              !isLoaded && (
                <p
                  className={styles.hint}
                  role="status"
                >
                  대화 기록을 불러오는 중…
                </p>
              )}

            {messages.length === 0 &&
              isLoaded &&
              !busy && (
                <p className={styles.hint}>
                  {npc.name}에게 자유롭게 질문해 보세요.
                  그날의 행적, 신기범과의 관계,
                  보고 들은 것, 다른 인물에 대한 생각 등
                  무엇이든 물을 수 있습니다.
                </p>
              )}

            {messages.map((message, i) => (
              <div
                key={message.id}
                className={[
                  styles.msg,
                  message.role === 'player'
                    ? styles.me
                    : styles.them,
                  i === lastNpcIdx ? styles.latestMsg : '',
                ].join(' ')}
              >
                {message.role === 'npc' && (
                  <CharacterPortrait
                    id={npc.id}
                    alt=""
                    className={styles.avatar}
                  />
                )}

                <div className={styles.bubbleWrap}>
                  {(message.role === 'npc' || embedded) && (
                    <span className={styles.who}>
                      {message.role === 'npc' ? npc.name : '수사관'}
                    </span>
                  )}

                  <p className={styles.bubble}>
                    {/* 방금 도착한 인물 답변(id가 t로 시작)만 한 번 타이핑 효과 */}
                    {message.role === 'npc' && message.id.startsWith('t') && !typed.has(message) ? (
                      <TypingText
                        text={message.text}
                        onTick={() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight }}
                        onDone={() => typed.add(message)}
                      />
                    ) : message.text}
                  </p>
                  {message.role === 'npc' && (
                    <button
                      type="button"
                      className={embedded ? styles.pin : styles.saveBtn}
                      data-tutorial="interview-save-statement"
                      aria-pressed={savedIds.has(`${npc.id}:${message.text}`)}
                      aria-label={savedIds.has(`${npc.id}:${message.text}`) ? '진술 저장 취소' : '진술 저장'}
                      title={embedded ? (savedIds.has(`${npc.id}:${message.text}`) ? '저장 취소' : '진술 저장') : undefined}
                      onClick={() => toggleStatement({ id: `${npc.id}:${message.text}`, npcId: npc.id, text: message.text, question: messages[i - 1]?.role === 'player' ? messages[i - 1].text : undefined })}
                    >
                      {embedded ? <Pin size={15} /> : savedIds.has(`${npc.id}:${message.text}`) ? '저장됨 ✓' : '진술 저장'}
                    </button>
                  )}
                </div>
              </div>
            ))}

            {/* NPC 답변 생성 중 */}

            {busy && typing === npcId && (
              <div
                className={`${styles.msg} ${styles.them}`}
              >
                <CharacterPortrait
                  id={npc.id}
                  alt=""
                  className={styles.avatar}
                />

                <div className={styles.bubbleWrap}>
                  <span className={styles.who}>
                    {npc.name}
                  </span>

                  <p
                    className={`${styles.bubble} ${styles.dots}`}
                    aria-label="답변 작성 중"
                  >
                    <i />
                    <i />
                    <i />
                  </p>
                </div>
              </div>
            )}

            {error && (
              <p
                className={styles.error}
                role="alert"
              >
                {error}

                {canRetry && (
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => void retry()}
                  >
                    다시 시도
                  </button>
                )}
              </p>
            )}
          </div>

          {/* ==================================================
              메시지 입력
              ================================================== */}

          <form
            className={styles.composer}
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            {hint && (
              <p className={`${styles.picked} ${styles.hintBox}`} role="status" data-tutorial="interview-hint-text">
                <Lightbulb size={14} />
                <span className={hint.error ? undefined : styles.hintText}>{hint.text}</span>
                <button type="button" onClick={() => setHint(null)} aria-label="힌트 닫기"><X size={14} /></button>
              </p>
            )}
            {draft.length > 0 && (
              <div className={styles.picked} data-tutorial="interview-picked">
                <FileSearch size={14} />
                {draft.map((id) => (
                  <span key={id} className={styles.chip}>
                    {evidence[id]?.title ?? id}
                    <button type="button" onClick={() => removeDraft(id)} aria-label={`${evidence[id]?.title ?? id} 빼기`}><X size={12} /></button>
                  </span>
                ))}
                <span>{overServer ? '두 증거 함께 제시는 서버 준비 중입니다. 하나를 빼 주세요.' : '질문을 함께 적거나 그대로 보내세요.'}</span>
              </div>
            )}
            <button
              type="button"
              className="btn"
              onClick={() => setPickOpen(true)}
              disabled={busy}
              data-tutorial="interview-present"
            >
              <FileSearch size={16} />
              증거 제시
            </button>

            {/* 통합 화면에서는 노트·힌트를 A의 상단·오른쪽 칸에서 연다 */}
            {!embedded && <><button
              type="button"
              className="btn"
              onClick={() =>
                useNoteStore.getState().setPanel(true)
              }
              data-tutorial="interview-notes"
            >
              <NotebookPen size={16} />
              추리 노트
            </button>

            <button
              type="button"
              className="btn"
              onClick={() => void askHint()}
              disabled={hintBusy}
              data-tutorial="interview-hint"
            >
              <Lightbulb size={16} />
              {hintBusy ? '힌트 찾는 중…' : '힌트'}
            </button></>}

            {/* Issue #59: 최대 200자 입력창 */}

            <div className={styles.inputRow}>
            <div className={styles.messageField} data-tutorial="interview-input">
              <textarea
                value={text}
                rows={1}
                maxLength={MAX_MESSAGE_LENGTH}
                placeholder={embedded ? `${npc.name}에게 질문하기` : `${npc.name}에게 질문하기 (Enter 전송 · Shift+Enter 줄바꿈)`}
                onChange={(event) =>
                  handleTextChange(event.target.value)
                }
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault()
                    submit()
                  }
                }}
                aria-label={`${npc.name}에게 질문 입력`}
                aria-describedby="npc-message-count"
              />

              <span
                id="npc-message-count"
                className={[
                  styles.charCount,
                  text.length >= MAX_MESSAGE_LENGTH
                    ? styles.charCountLimit
                    : '',
                ].join(' ')}
              >
                {text.length} / {MAX_MESSAGE_LENGTH}
              </span>
            </div>

            <button
              type="submit"
              className={`${styles.send} ${draft.length ? styles.sendPresent : ''}`}
              disabled={
                busy ||
                (!text.trim() && !draft.length) ||
                overServer ||
                text.length > MAX_MESSAGE_LENGTH
              }
              aria-label={draft.length ? `${npc.name}에게 제시` : '보내기'}
            >
              {draft.length > 0 && <span>{npc.name}에게 제시</span>}
              <Send size={18} />
            </button>
            </div>
          </form>
        </section>
      </main>

      {/* ======================================================
          증거 제시 모달
          ====================================================== */}

      <AnimatePresence>
        {pickOpen && (
          <motion.div
            className={styles.backdrop}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closePick}
          >
            <motion.div
              className={`${styles.modal} ${sideBySide ? styles.modalWide : ''}`}
              role="dialog"
              aria-label="증거 제시"
              initial={{
                y: 20,
                opacity: 0,
              }}
              animate={{
                y: 0,
                opacity: 1,
              }}
              exit={{
                y: 20,
                opacity: 0,
              }}
              onClick={(event) =>
                event.stopPropagation()
              }
            >
              <header>
                <h3 className="serif">
                  {npc.name}에게 제시할 증거
                </h3>

                <button
                  type="button"
                  onClick={closePick}
                  aria-label="닫기"
                >
                  <X size={18} />
                </button>
              </header>

              {sideBySide ? (
                <>
                  <EvidenceCompare ids={draft} />
                  <footer className={styles.modalFoot}>
                    <button type="button" className="btn" onClick={() => setSideBySide(false)}>목록으로</button>
                    <button type="button" className="btn btn--primary" onClick={closePick}>제시</button>
                  </footer>
                </>
              ) : found.length === 0 ? (
                <p className={styles.none}>
                  아직 확보한 증거가 없습니다.
                  인물들에게 질문하며 단서를 찾아보세요.
                </p>
              ) : (
                <>
                  <p className={styles.none} aria-live="polite">한 번에 최대 {MAX_DRAFT}개까지 고를 수 있습니다 · {draft.length} / {MAX_DRAFT}</p>
                  <ul>
                    {found.map((id) => {
                      const on = draft.includes(id)
                      return (
                        <li key={id}>
                          <button
                            type="button"
                            aria-pressed={on}
                            disabled={!on && draft.length >= MAX_DRAFT}
                            onClick={() => (on ? removeDraft(id) : addDraft(id))}
                          >
                            <FileSearch size={16} />
                            <span>{evidence[id]?.title ?? id}</span>
                            {on && <i className={styles.pickNo}>{draft.indexOf(id) + 1}</i>}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                  <footer className={styles.modalFoot}>
                    <button type="button" className="btn" disabled={draft.length < 2} title={draft.length < 2 ? '증거 2개를 고르면 나란히 볼 수 있습니다.' : undefined} onClick={() => { draft.forEach((id) => void loadEvidence(id)); setSideBySide(true) }}>나란히 보기</button>
                    <button type="button" className="btn btn--primary" disabled={!draft.length} onClick={closePick}>제시</button>
                  </footer>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Shell({ embedded = false }: { embedded?: boolean }) {
  return (
    <div className={`${styles.page} ${embedded ? styles.embedded : ''}`}>
      {!embedded && <TopNav />}
    </div>
  )
}
