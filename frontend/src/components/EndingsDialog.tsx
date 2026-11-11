import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Lock, X } from 'lucide-react'
import { ENDINGS, loadEndingScene, loadSeenEndings, type EndingKey } from '../data/endings'
import { defaultScene, type SceneLine } from '../data/endingScenes'
import EndingScene from './EndingScene'
import styles from './EndingsDialog.module.css'

/** 엔딩 기록: 본 엔딩은 이름과 한 줄 요약, 못 본 엔딩은 잠긴 칸으로만 보여준다 */
export default function EndingsDialog({ current, onClose }: { current?: EndingKey; onClose: () => void }) {
  const seen = loadSeenEndings()
  const [replay, setReplay] = useState<SceneLine[] | null>(null)
  const play = (k: EndingKey) => setReplay(loadEndingScene(k) ?? defaultScene(k, '관계자'))
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !replay) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, replay])
  return (
    <>
    {!replay && <motion.div className={styles.backdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} onClick={onClose}>
      <div className={styles.modal} role="dialog" aria-label="엔딩 기록" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 className="serif">엔딩 기록 <small>{seen.length} / {ENDINGS.length}</small></h2>
          <button type="button" onClick={onClose} aria-label="닫기" autoFocus><X size={18} /></button>
        </header>
        <ul>
          {ENDINGS.map((e, i) => {
            const got = seen.includes(e.key)
            return (
              <li key={e.key} className={got ? styles.got : styles.lock}>
                <span className={styles.no}>{String(i + 1).padStart(2, '0')}</span>
                {got ? (
                  <div>
                    <b className="serif">{e.label}{current === e.key && <em>방금 본 엔딩</em>}</b>
                    <p>{e.summary}</p>
                    <button type="button" className={styles.replay} onClick={() => play(e.key)}>다시 보기 ▸</button>
                  </div>
                ) : (
                  <div>
                    <b className="serif"><Lock size={14} aria-hidden="true" /> ???</b>
                    <p>아직 보지 못한 엔딩입니다.</p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
        <p className={styles.note}>엔딩 기록은 이 기기에 저장되며 새로 시작해도 유지됩니다.</p>
      </div>
    </motion.div>}
    {replay && <EndingScene lines={replay} onDone={() => setReplay(null)} />}
    </>
  )
}
