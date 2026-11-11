import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import CharacterPortrait from './CharacterPortrait'
import { NPC_PUBLIC } from '../data/characters'
import styles from './EndingScene.module.css'

import type { SceneLine } from '../data/endingScenes'
export type { SceneLine }

/** 엔딩 대화 장면: 클릭·Enter·Space로 한 줄씩 넘긴다. 대사 내용은 서버가 준 것만 표시한다. */
export default function EndingScene({ lines, onDone }: { lines: SceneLine[]; onDone: () => void; fallbackId?: string }) {
  const [i, setI] = useState(0)
  const line = lines[i]
  const npc = NPC_PUBLIC.find((n) => n.id === line?.speaker)
  const label = npc ? npc.name : line && line.speaker !== 'narration' ? line.speaker : null
  const last = i >= lines.length - 1
  // 해설 줄에서도 화면이 비지 않게: 지금까지 말한 마지막 인물, 없으면 지목한 인물을 보여준다
  const prev = [...lines.slice(0, i + 1)].reverse().find((l) => NPC_PUBLIC.some((n) => n.id === l.speaker))?.speaker
  const shownId = npc?.id ?? prev
  const showInvestigator = line?.speaker === '수사관' && !line.image && !line.evidenceSrc
  const shown = line?.image || line?.evidenceSrc || line?.speaker === '수사관' ? undefined : NPC_PUBLIC.find((n) => n.id === shownId)
  const bg = line?.image ? `${import.meta.env.BASE_URL}${line.image}` : null

  const next = useCallback(() => { if (last) onDone(); else setI((v) => v + 1) }, [last, onDone])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof Element && e.target.closest('button') && e.target.closest('[aria-label="엔딩 대화"]')) return
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); next() }
      else if (e.key === 'Escape') onDone()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, onDone])

  if (!line) return null
  return (
    <div className={`${styles.root} ${line.card ? styles.cardMode : ''}`} onClick={next} role="dialog" aria-label="엔딩 대화">
      <h1 className="sr-only">엔딩</h1>
      <div className={styles.stage}>
        <AnimatePresence mode="wait">
          {bg && (
            <motion.img key={bg} className={styles.scene} src={bg} alt={line.card ? line.text : ''} draggable={false} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.7 }} />
          )}
          {line.evidenceSrc && (
            <motion.img key={line.evidenceSrc} className={styles.evidence} src={line.evidenceSrc} alt="제시한 증거 사진" draggable={false} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }} />
          )}
          {showInvestigator && (
            <motion.div key="investigator" className={styles.portrait} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }}>
              <img src={`${import.meta.env.BASE_URL}assets/characters/investigator.webp`} alt="수사관" draggable={false} onError={(e) => { e.currentTarget.style.display = 'none' }} />
            </motion.div>
          )}
          {shown && (
            <motion.div key={shown.id} className={styles.portrait} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }}>
              <CharacterPortrait id={shown.id} alt={`${shown.name}의 모습`} standing />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <button type="button" className="scene-skip" onClick={(e) => { e.stopPropagation(); onDone() }}>건너뛰기</button>
      {line.card ? (
        <div className={styles.cardBar}>
          <span className={styles.more}>클릭하여 결과 보기 ▾ <i>{i + 1} / {lines.length}</i></span>
        </div>
      ) : (
      <div className={styles.box} aria-live="polite">
        <AnimatePresence mode="wait">
          <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            {label ? <b className={`serif ${styles.name}`}>{label}</b> : null}
            <p className={label ? styles.say : styles.narr}>{line.text}</p>
          </motion.div>
        </AnimatePresence>
        <span className={styles.more}>{last ? '클릭하여 결과 보기 ▾' : '클릭하여 계속 ▾'} <i>{i + 1} / {lines.length}</i></span>
      </div>
      )}
    </div>
  )
}
