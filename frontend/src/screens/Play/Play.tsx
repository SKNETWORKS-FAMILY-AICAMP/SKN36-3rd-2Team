import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import GameHelp from '../../components/GameHelp'
import FieldTutorial, { type FieldTutorialStep } from '../../components/FieldTutorial'
import Toasts from '../../components/Toasts'
import { api } from '../../api/client'
import { ApiHttpError } from '../../api/httpApi'
import { investigate } from '../../api/investigationApi'
import { getObjectives, objectiveLabel, objectiveStatusLabel, type ObjectiveItem } from '../../api/objectiveApi'
import { useGameStore } from '../../store/gameStore'
import { useNoteStore } from '../../store/noteStore'
import { backgroundUrl, fieldPlaces, fieldSubviews, floorMaps, zoomUrl, type Hotspot, type MapRoom } from '../../data/fieldScenes'
import styles from './Play.module.css'

function Panel({ title, kind, children, onClose }: { title: string; kind: Modal['kind']; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el && !el.open) el.showModal()
    return () => { if (el?.open) el.close() }
  }, [])
  return (
    <dialog ref={ref} className={`${styles.dialog} ${kind === 'map' ? styles.mapDialog : kind === 'hint' ? styles.hintDialog : styles.detailDialog}`} onCancel={(event) => { event.preventDefault(); onClose() }} aria-label={title}>
      <div className={styles.dialogHead}><h2>{title}</h2><button type="button" onClick={onClose}>닫기 ×</button></div>
      {children}
    </dialog>
  )
}

type Modal = { kind: 'map' } | { kind: 'hint' } | { kind: 'zoom'; hotspot: Hotspot } | { kind: 'room'; room: MapRoom }

export default function Play() {
  const navigate = useNavigate()
  const session = useGameStore((s) => s.session)
  const setPanel = useNoteStore((s) => s.setPanel)
  const [placeId, setPlaceId] = useState('lobby')
  const [subviewId, setSubviewId] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [observations, setObservations] = useState<string[]>([])
  const [hint, setHint] = useState('')
  const [hintBusy, setHintBusy] = useState(false)
  const hintLock = useRef(false)
  const [fieldBusy, setFieldBusy] = useState(false)
  const [fieldStatus, setFieldStatus] = useState('')
  const fieldLock = useRef(false)

  const sessionId = session?.sessionId
  const phase = session?.phase
  const [tutorialStep, setTutorialStep] = useState<FieldTutorialStep | null>(null)
  useEffect(() => {
    if (!sessionId || phase !== 'INVESTIGATION') {
      setTutorialStep(null)
      return
    }
    let seen = false
    try { seen = localStorage.getItem(`serin-field-guide-v1:${sessionId}`) === 'done' } catch { /* 저장소 사용 불가 */ }
    setTutorialStep(seen ? null : 'inspect')
  }, [sessionId, phase])

  const finishFieldTutorial = () => {
    if (sessionId && phase === 'INVESTIGATION') {
      try { localStorage.setItem(`serin-field-guide-v1:${sessionId}`, 'done') } catch { /* 현재 화면에서만 종료 */ }
    }
    setTutorialStep(null)
  }

  const closePanel = () => {
    if (fieldLock.current) return
    if (modal?.kind === 'zoom' && tutorialStep === 'inspect') setTutorialStep('room')
    setModal(null)
  }
  const revision = session?.revision
  const [objectiveState, setObjectiveState] = useState<{
    sessionId: string
    revision: number | undefined
    items: ObjectiveItem[]
    error: boolean
  } | null>(null)
  const [objectiveRetry, setObjectiveRetry] = useState(0)

  useEffect(() => {
    if (!sessionId) return
    let active = true
    setObjectiveState(null)
    void getObjectives(sessionId)
      .then((items) => {
        if (active) setObjectiveState({ sessionId, revision, items, error: false })
      })
      .catch(() => {
        if (active) setObjectiveState({ sessionId, revision, items: [], error: true })
      })
    return () => { active = false }
  }, [sessionId, revision, objectiveRetry])

  const currentObjectives = objectiveState?.sessionId === sessionId && objectiveState?.revision === revision
    ? objectiveState : null
  const objectiveItems = currentObjectives?.items ?? []
  const fallbackGoal = subviewId ? '세부 공간을 살펴보세요.' : '조사 지점을 선택해 현장을 살펴보세요.'
  const activeGoal = objectiveItems.find((item) => objectiveStatusLabel(item.status) === '진행 중')

  // 장소 해금 API가 확인되기 전까지 전체 장소 탐색은 개발 모드에서만 허용합니다.
  // 실제 증거 획득은 서버 조사 API의 응답만 사용합니다.
  const preview = import.meta.env.DEV
  const availablePlaces = preview ? fieldPlaces : fieldPlaces.filter((p) => p.id === 'lobby')
  const place = availablePlaces.find((p) => p.id === placeId) ?? availablePlaces[0]
  const scene = subviewId && fieldSubviews[subviewId] ? fieldSubviews[subviewId] : place

  const selectPlace = (id: string) => {
    if (id === 'interview') {
      if (session?.phase === 'INVESTIGATION' && session.unlockedNpcs.length > 0) {
        setModal(null)
        if (tutorialStep !== null) finishFieldTutorial()
        navigate('/chat')
      }
      return
    }
    if (!availablePlaces.some((p) => p.id === id)) return
    setPlaceId(id)
    setSubviewId(null)
    setModal(null)
  }

  const inspect = (hotspot: Hotspot) => {
    if (hotspot.subview) {
      setSubviewId(hotspot.subview)
      return
    }
    setFieldStatus('')
    setObservations((old) => {
      const item = `${scene.name} · ${hotspot.label} 살펴봄`
      return old.includes(item) ? old : [...old, item]
    })
    if (hotspot.zoom) setModal({ kind: 'zoom', hotspot })
  }

  const runInvestigation = async (actionId: string) => {
    const current = useGameStore.getState().session
    if (!current || current.phase !== 'INVESTIGATION' || fieldLock.current) return
    fieldLock.current = true
    setFieldBusy(true)
    setFieldStatus('서버에서 조사 결과를 확인하는 중입니다.')
    try {
      const result = await investigate(current.sessionId, actionId)
      if (useGameStore.getState().session?.sessionId !== current.sessionId) return
      try {
        await useGameStore.getState().handleEvents(result.created
          ? [{ type: 'evidence_found', id: result.evidenceId }]
          : [])
        setFieldStatus(result.created ? '새 증거를 확보했습니다. 증거함에서 확인하세요.' : '이미 확보한 조사 자료입니다.')
      } catch {
        setFieldStatus('서버에 조사 결과가 저장되었지만 화면 갱신에 실패했습니다. 상태를 다시 확인해 주세요.')
      }
    } catch (error) {
      if (error instanceof ApiHttpError) {
        if (error.status === 409) {
          if (useGameStore.getState().session?.sessionId === current.sessionId) {
            await useGameStore.getState().refresh().catch(() => undefined)
          }
          setFieldStatus('게임 상태가 변경되었거나 현재 조사할 수 없습니다. 상태를 확인해 주세요.')
        } else if (error.status === 403) {
          setFieldStatus('아직 조사할 수 없는 자료입니다. 다른 단서나 면담을 확인하세요.')
        } else if (error.status === 404) {
          setFieldStatus('아직 서버에서 제공하지 않는 조사 자료입니다.')
        } else if (error.status === 503) {
          setFieldStatus('서버 콘텐츠를 이용할 수 없습니다.')
        } else {
          setFieldStatus('조사 요청에 실패했습니다. 서버 상태를 확인해 주세요.')
        }
      } else {
        setFieldStatus('조사 결과를 확인하지 못했습니다. 상태를 먼저 확인해 주세요.')
      }
    } finally {
      fieldLock.current = false
      setFieldBusy(false)
    }
  }

  const syncFieldState = async () => {
    if (fieldLock.current || !useGameStore.getState().session) return
    fieldLock.current = true
    setFieldBusy(true)
    try {
      await useGameStore.getState().refresh()
      setFieldStatus('서버 게임 상태를 갱신했습니다.')
    } catch {
      setFieldStatus('서버 게임 상태를 갱신하지 못했습니다.')
    } finally {
      fieldLock.current = false
      setFieldBusy(false)
    }
  }

  const selectRoom = (room: MapRoom) => {
    if (room.place && availablePlaces.some((p) => p.id === room.place)) {
      selectPlace(room.place)
    } else if (room.place === 'interview' && session?.phase === 'INVESTIGATION' && session.unlockedNpcs.length > 0) {
      selectPlace('interview')
    } else {
      setModal({ kind: 'room', room })
    }
  }

  const requestHint = async () => {
    if (!session || session.phase !== 'INVESTIGATION' || hintLock.current) return
    hintLock.current = true
    setHintBusy(true)
    setHint('')
    try { setHint(await api.getHint(session.sessionId)) }
    catch (error) { setHint(error instanceof Error ? error.message : '힌트를 불러오지 못했습니다.') }
    finally { hintLock.current = false; setHintBusy(false) }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div><small>CASE 001 · SERIN ARCHIVE</small><h1>마지막 기록: 졸업하지 못한 밤</h1></div>
        <span>{session?.currentChapter ?? ''}</span>
        <div className={styles.actions}>
          <button type="button" data-tutorial="field-map" onClick={() => setModal({ kind: 'map' })}>설계도</button>
          <button type="button" data-tutorial="field-goal" onClick={() => setModal({ kind: 'hint' })}>목표 · 힌트</button>
          <button type="button" onClick={() => setHelpOpen(true)}>도움말</button>
          <button type="button" onClick={() => { setPlaceId('lobby'); setSubviewId(null); setModal(null); setTutorialStep('inspect') }}>현장 튜토리얼</button>
          {session?.canAccuse && <button type="button" onClick={() => navigate('/accuse')}>최종 추리</button>}
        </div>
      </header>
      <div className={styles.layout}>
        <aside className={styles.sidebar} data-tutorial="field-place-list">
          <h3>조사 장소</h3>
          {availablePlaces.map((p) => (
            <button key={p.id} type="button" className={place.id === p.id ? styles.active : ''} onClick={() => selectPlace(p.id)} aria-pressed={place.id === p.id}>
              {p.name}<small>{p.floor}</small>
            </button>
          ))}
          <h3>면담</h3>
          <button type="button" data-tutorial="field-interview" disabled={session?.phase !== 'INVESTIGATION' || !session.unlockedNpcs.length} onClick={() => selectPlace('interview')}>면담실<small>2층</small></button>
        </aside>
        <main className={styles.main}>
          {preview && <p className={styles.preview}>개발용 화면 탐색 · 장소 해금 미연동. 일부 조사 지점은 서버 API로 연결했습니다.</p>}
          <div className={styles.notice} role="status">지금 할 일 · {activeGoal ? objectiveLabel(activeGoal.objectiveId) : fallbackGoal}</div>
          <div className={styles.titlebar}>
            <h2>{scene.name} <small>{scene.floor}</small></h2>
            {subviewId && <button type="button" onClick={() => setSubviewId(null)}>← {place.name}으로 돌아가기</button>}
          </div>
          <div className={styles.scene} data-tutorial="field-scene">
            <img className={styles.background} src={backgroundUrl(scene.image)} alt={`${scene.name} 배경`} draggable={false} />
            {scene.hotspots.map((h) => (
              <button key={h.id} type="button" className={styles.hotspot} style={{ left: `${h.x}%`, top: `${h.y}%`, transform: `translate(${h.x >= 80 ? '-100%' : h.x <= 17 ? '0%' : '-50%'}, -50%)` }}
                data-tutorial={scene.hotspots.find((point) => point.zoom)?.id === h.id ? 'field-hotspot' : undefined} onClick={() => inspect(h)} aria-label={h.label}>
                <span className={styles.dot} aria-hidden="true" /> <span className={styles.hotLabel}>{h.label}</span>
              </button>
            ))}
          </div>
          <details className={styles.records}>
            <summary>현장 기록 · {observations.length}건</summary>
            {observations.length === 0 ? <p>아직 살펴본 조사 지점이 없습니다.</p> : <ul>{observations.map((item) => <li key={item}>{item}</li>)}</ul>}
          </details>
        </main>
        <nav className={styles.tools}>
          <h3>수사 도구</h3>
          <button type="button" data-tutorial="field-evidence" onClick={() => navigate('/evidence')}>증거함 · {session?.foundEvidence.length ?? 0}개</button>
          <button type="button" onClick={() => navigate('/relations')}>인물관계도</button>
          <button type="button" onClick={() => setPanel(true)}>수사 기록</button>
        </nav>
      </div>
      <Toasts />
      {tutorialStep && !modal && !helpOpen && <FieldTutorial step={tutorialStep} onSkip={finishFieldTutorial} /> }
      <GameHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      {modal && <Panel kind={modal.kind} title={modal.kind === 'map' ? '설계도 · 구 본관' : modal.kind === 'hint' ? '목표 · 힌트' : modal.kind === 'zoom' ? modal.hotspot.label : modal.room.name} onClose={closePanel}>
        {modal.kind === 'map' && <>
          <div className={styles.plans}>
            {floorMaps.map((floor) => <section key={floor.name} className={styles.plan}><h3>{floor.name}</h3>
              {floor.rooms.map((room, i) => <button key={`${room.name}-${i}`} type="button" className={`${styles.room} ${room.place ? styles.roomPlace : ''}`}
                style={{ left: `${room.rect[0]}%`, top: `${room.rect[1]}%`, width: `${room.rect[2]}%`, height: `${room.rect[3]}%` }} onClick={() => selectRoom(room)}>
                <img src={backgroundUrl(room.image)} alt="" loading="lazy" /><span>{room.name}</span>
              </button>)}
            </section>)}
          </div>
          <p className={styles.preview}>건물 구조 안내입니다. 실제 이동·해금 가능 여부는 서버 연결 후 반영합니다.</p>
        </>}
        {modal.kind === 'room' && <><img className={styles.detailImage} src={backgroundUrl(modal.room.image)} alt={modal.room.name} /><p>{modal.room.description ?? '서버 장소 이동 연결 전의 구조 안내입니다.'}</p><button type="button" onClick={() => setModal({ kind: 'map' })}>← 설계도로 돌아가기</button></>}
        {modal.kind === 'zoom' && modal.hotspot.zoom && <><img className={styles.detailImage} src={zoomUrl(modal.hotspot.zoom)} alt={`${modal.hotspot.label} 확대`} />{modal.hotspot.actions?.length ? <>
          <p>조사 결과는 서버가 확인합니다.</p>
          {modal.hotspot.actions.map((action) => <button key={action.id} type="button" disabled={fieldBusy || session?.phase !== 'INVESTIGATION'} onClick={() => void runInvestigation(action.id)}>{action.label}</button>)}
          {session?.phase !== 'INVESTIGATION' && <p>오프닝을 완료한 실제 게임 세션에서 조사할 수 있습니다.</p>}
          {fieldStatus && <p role="status">{fieldStatus}</p>}
          {session && <button type="button" disabled={fieldBusy} onClick={() => void syncFieldState()}>상태 다시 확인</button>}
        </> : <p>확대 관찰 화면 · 서버 조사 연결은 아직 준비 중입니다.</p>}</>}
        {modal.kind === 'hint' && <><h3>현재 목표</h3>
          {!sessionId ? <p>{fallbackGoal} (게임 세션 연결 전)</p>
            : !currentObjectives ? <p role="status">목표를 불러오는 중입니다.</p>
            : currentObjectives.error ? <><p>{fallbackGoal}</p><p role="status">서버 목표를 불러오지 못했습니다.</p></>
            : objectiveItems.length === 0 ? <p>{fallbackGoal} (서버에서 제공한 목표 없음)</p>
            : <ul>{objectiveItems.map((item) => <li key={item.objectiveId}>{objectiveLabel(item.objectiveId)} · {objectiveStatusLabel(item.status)}</li>)}</ul>}
          {sessionId && <button type="button" onClick={() => setObjectiveRetry((n) => n + 1)}>목표 다시 확인</button>}
          <h3>힌트</h3><p>{hint || '서버에서 1단계 힌트를 요청할 수 있습니다.'}</p><button type="button" disabled={!session || session.phase !== 'INVESTIGATION' || hintBusy} onClick={() => void requestHint()}>{hintBusy ? '불러오는 중…' : '힌트 확인'}</button></>}
      </Panel>}
    </div>
  )
}
