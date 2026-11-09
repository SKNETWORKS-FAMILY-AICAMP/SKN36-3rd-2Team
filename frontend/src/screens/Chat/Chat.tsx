import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { FileSearch, Lock, NotebookPen, Send, X } from 'lucide-react'
import TopNav from '../../components/TopNav'
import Toasts from '../../components/Toasts'
import CharacterPortrait from '../../components/CharacterPortrait'
import { NPC_PUBLIC, npcName } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import { useChatStore } from '../../store/chatStore'
import { useNoteStore } from '../../store/noteStore'
import { mockDebug } from '../../api/mockApi'
import { api, apiMode } from '../../api/client'
import type { AvailableEvidence } from '../../api/types'
import styles from './Chat.module.css'

const EMPTY: never[] = []

export default function Chat() {
  const { npcId } = useParams()
  const navigate = useNavigate()
  const { search } = useLocation()
  const [params] = useSearchParams()
  const debug = params.has('debug')

  const session = useGameStore((s) => s.session)
  const ensure = useGameStore((s) => s.ensureSession)
  const evidence = useGameStore((s) => s.evidence)
  const refresh = useGameStore((s) => s.refresh)

  const messages = useChatStore((s) => (npcId ? s.messages[npcId] ?? EMPTY : EMPTY))
  const allMessages = useChatStore((s) => s.messages)
  const typing = useChatStore((s) => s.typing)
  const isLoaded = useChatStore((s) => (npcId ? !!s.loaded[npcId] : true))
  const error = useChatStore((s) => s.error)
  const load = useChatStore((s) => s.load)
  const retry = useChatStore((s) => s.retry)
  const canRetry = useChatStore((s) => s.canRetry)
  const send = useChatStore((s) => s.send)
  const present = useChatStore((s) => s.present)

  const [text, setText] = useState('')
  const [pickOpen, setPickOpen] = useState(false)
  const [available, setAvailable] = useState<AvailableEvidence[]>([])
  const [collecting, setCollecting] = useState<string | null>(null)
  const collectingRef = useRef(false)
  const [collectError, setCollectError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => { void ensure() }, [ensure])

  const sid = session?.sessionId
  useEffect(() => {
    if (sid && npcId) void load(npcId)
  }, [sid, npcId, load])

  // 다른 인물과의 이전 대화 여부를 폴라로이드에 표시하기 위해 해금된 인물의 기록을 미리 불러온다
  const unlockedKey = session?.unlockedNpcs.join()
  useEffect(() => {
    if (!sid) return
    session?.unlockedNpcs.forEach((id) => { if (id !== npcId) void load(id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, unlockedKey])

  // 새 메시지나 입력 중 표시가 생기면 맨 아래로
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, typing])


  // Evidence availability is calculated by server policies after NPC dialogue.
  const activeRevision = session?.revision
  const activeNpcId = session?.activeCharacterId
  useEffect(() => {
    if (
      apiMode !== 'http' || !sid || !npcId ||
      session?.phase !== 'INVESTIGATION' || activeNpcId !== npcId
    ) {
      setAvailable([])
      return
    }
    let active = true
    api.getAvailableEvidence(sid)
      .then((items) => { if (active) setAvailable(items) })
      .catch(() => { if (active) setAvailable([]) })
    return () => { active = false }
  }, [sid, npcId, activeRevision, activeNpcId, session?.phase])

  const collect = async (evidenceId: string) => {
    if (!sid || typing !== null || collectingRef.current) return
    collectingRef.current = true
    setCollecting(evidenceId)
    setCollectError(null)
    try {
      const events = await api.collectEvidence(sid, evidenceId)
      await useGameStore.getState().handleEvents(events)
      setAvailable(await api.getAvailableEvidence(sid))
    } catch (error) {
      // A 409 may mean another request succeeded; never blindly retry a mutation.
      try { await useGameStore.getState().refresh() } catch { /* retain session */ }
      setCollectError(error instanceof Error ? error.message : '증거 확보에 실패했습니다.')
    } finally {
      collectingRef.current = false
      setCollecting(null)
    }
  }

  const unlocked = session?.unlockedNpcs ?? []
  const npc = useMemo(() => NPC_PUBLIC.find((n) => n.id === npcId), [npcId])

  if (!npcId) return session ? <Navigate to={{ pathname: `/chat/${unlocked[0] ?? 'C01'}`, search }} replace /> : <Shell />
  if (!npc) return <Navigate to={{ pathname: '/chat', search }} replace />
  if (session && !unlocked.includes(npcId)) return <Navigate to={{ pathname: '/chat', search }} replace />

  const found = session?.foundEvidence ?? []
  const busy = typing !== null || collecting !== null
  const submit = () => {
    const t = text.trim()
    if (!t || busy || !session) return
    setText('')
    void send(npcId, t)
  }

  return (
    <div className={styles.page}>
      <TopNav />
      <Toasts />

      <ul className={styles.row} aria-label="인물 선택">
        {NPC_PUBLIC.map((n) => {
          const open = unlocked.includes(n.id)
          const active = n.id === npcId
          return (
            <li key={n.id}>
              <button
                type="button"
                disabled={!open || busy}
                className={`${styles.polaroid} ${active ? styles.current : ''} ${open ? '' : styles.locked}`}
                onClick={() => navigate({ pathname: `/chat/${n.id}`, search })}
                aria-current={active}
                aria-label={open ? n.name : '아직 만날 수 없는 인물'}
              >
                <span className={styles.photo}>
                  {open ? <CharacterPortrait id={n.id} alt="" /> : <Lock size={20} />}
                  {open && (allMessages[n.id]?.length ?? 0) > 0 && (
                    <i className={styles.talked} aria-label="이전 대화 있음" />
                  )}
                </span>
                <span className={styles.cap}>{open ? n.name : '???'}</span>
              </button>
            </li>
          )
        })}
      </ul>

      <main className={styles.main}>
        <aside className={styles.profile}>
          <div className={styles.frame}>
            <span className={styles.tape} aria-hidden="true" />
            <CharacterPortrait id={npc.id} alt={`${npc.name}의 사진`} className={styles.portrait} standing />
          </div>
          <div className={styles.info}>
            <h2 className="serif">{npc.name}</h2>
            <p className={styles.role}>{npc.title}</p>
            <dl>
              <div><dt>나이대</dt><dd>{npc.age}</dd></div>
              <div><dt>외형</dt><dd>{npc.look}</dd></div>
              <div><dt>말투</dt><dd>{npc.tone}</dd></div>
            </dl>
          </div>
        </aside>

        <section className={styles.chat} aria-label={`${npc.name}와의 대화`}>
          <header className={styles.chatHead}>
            <b className="serif">{npc.name}</b>
            <span>{npc.title}</span>
            <em>{messages.length > 0 ? `이전 대화 ${messages.filter((m) => m.role === 'player').length}회` : '첫 대화'}</em>
          </header>
          {apiMode === 'http' && (available.length > 0 || collectError) && (
            <div className={styles.collectPanel} role="region" aria-label="확보 가능한 증거">
              {available.length > 0 && <strong>새로운 단서가 확인됐습니다</strong>}
              {available.map((item) => (
                <button
                  type="button"
                  key={item.evidenceId}
                  className={styles.collectButton}
                  disabled={busy}
                  onClick={() => void collect(item.evidenceId)}
                >
                  <FileSearch size={15} />
                  {item.evidenceId} · {item.name} 확보 (+{item.score}점)
                </button>
              ))}
              {collectError && <span className={styles.collectError} role="alert">{collectError}</span>}
            </div>
          )}
          <div className={styles.list} ref={listRef}>
            {messages.length === 0 && !isLoaded && (
              <p className={styles.hint} role="status">대화 기록을 불러오는 중…</p>
            )}
            {messages.length === 0 && isLoaded && !busy && (
              <p className={styles.hint}>
                {npc.name}에게 자유롭게 질문해 보세요. 그날의 행적, 신기범과의 관계, 보고 들은 것, 다른 인물에 대한 생각 등 무엇이든 물을 수 있습니다.
              </p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`${styles.msg} ${m.role === 'player' ? styles.me : styles.them}`}>
                {m.role === 'npc' && (
                  <CharacterPortrait id={npc.id} alt="" className={styles.avatar} />
                )}
                <div className={styles.bubbleWrap}>
                  {m.role === 'npc' && <span className={styles.who}>{npc.name}</span>}
                  <p className={styles.bubble}>{m.text}</p>
                </div>
              </div>
            ))}
            {busy && typing === npcId && (
              <div className={`${styles.msg} ${styles.them}`}>
                <CharacterPortrait id={npc.id} alt="" className={styles.avatar} />
                <div className={styles.bubbleWrap}>
                  <span className={styles.who}>{npc.name}</span>
                  <p className={`${styles.bubble} ${styles.dots}`} aria-label="답변 작성 중">
                    <i /><i /><i />
                  </p>
                </div>
              </div>
            )}
            {error && (
              <p className={styles.error} role="alert">
                {error}
                {canRetry && <button type="button" className="btn btn--sm" onClick={() => void retry()}>다시 시도</button>}
              </p>
            )}
          </div>

          <form
            className={styles.composer}
            onSubmit={(e) => { e.preventDefault(); submit() }}
          >
            <button
              type="button"
              className="btn"
              onClick={() => setPickOpen(true)}
              disabled={busy}
            >
              <FileSearch size={16} /> 증거 제시
            </button>
            <button type="button" className="btn" onClick={() => useNoteStore.getState().setPanel(true)}>
              <NotebookPen size={16} /> 추리 노트
            </button>
            <textarea
              value={text}
              rows={1}
              placeholder={`${npc.name}에게 질문하기 (Enter 전송 · Shift+Enter 줄바꿈)`}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  submit()
                }
              }}
            />
            <button type="submit" className={styles.send} disabled={busy || !text.trim()} aria-label="보내기">
              <Send size={18} />
            </button>
          </form>
        </section>
      </main>

      <AnimatePresence>
        {pickOpen && (
          <motion.div
            className={styles.backdrop}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setPickOpen(false)}
          >
            <motion.div
              className={styles.modal}
              role="dialog"
              aria-label="증거 제시"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 20, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <header>
                <h3 className="serif">{npc.name}에게 제시할 증거</h3>
                <button type="button" onClick={() => setPickOpen(false)} aria-label="닫기"><X size={18} /></button>
              </header>
              {found.length === 0 ? (
                <p className={styles.none}>아직 확보한 증거가 없습니다. 인물들에게 질문하며 단서를 찾아보세요.</p>
              ) : (
                <ul>
                  {found.map((id) => (
                    <li key={id}>
                      <button
                        type="button"
                        onClick={() => {
                          setPickOpen(false)
                          void present(npcId, id, evidence[id]?.title ?? id)
                        }}
                      >
                        <FileSearch size={16} />
                        <span>{evidence[id]?.title ?? id}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {debug && (
        <div className={styles.debug}>
          <strong>DEBUG</strong>
          <button type="button" onClick={() => { mockDebug.unlockAll(); void refresh() }}>전원 해금</button>
          <button type="button" onClick={() => { mockDebug.grantDemoEvidence(); void refresh() }}>증거 획득</button>
          <button type="button" onClick={() => { mockDebug.grantAllEvidence(); void refresh() }}>증거 10칸</button>
          <button type="button" onClick={() => { mockDebug.reset(); location.reload() }}>초기화</button>
          <span>{session?.collection.score}/{session?.collection.total} · {npcName(npcId)}</span>
        </div>
      )}
    </div>
  )
}

function Shell() {
  return (
    <div className={styles.page}>
      <TopNav />
    </div>
  )
}
