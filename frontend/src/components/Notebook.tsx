import { useState } from 'react'
import { NOTE_SECTIONS, useNoteStore, type NoteKey } from '../store/noteStore'
import styles from './Notebook.module.css'

// 직접 쓰는 빈 노트. 시스템이 내용을 채우지 않는다.
export default function Notebook({ compact = false }: { compact?: boolean }) {
  const notes = useNoteStore((s) => s.notes)
  const setNote = useNoteStore((s) => s.setNote)
  const [active, setActive] = useState<NoteKey>('people')
  const section = NOTE_SECTIONS.find((s) => s.key === active)!

  return (
    <div className={`${styles.book} ${compact ? styles.compact : ''}`}>
      <div className={styles.tabs} role="tablist" aria-label="노트 항목">
        {NOTE_SECTIONS.map((s, i) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={s.key === active}
            className={`${styles.tab} ${s.key === active ? styles.on : ''}`}
            onClick={() => setActive(s.key)}
          >
            <b>{i + 1}</b> {s.title}
            {notes[s.key].trim() && <i aria-label="작성됨" />}
          </button>
        ))}
      </div>
      <div className={styles.page}>
        <h3 className="serif">{section.title}</h3>
        <textarea
          key={active}
          value={notes[active]}
          placeholder={section.hint}
          onChange={(e) => setNote(active, e.target.value)}
          spellCheck={false}
        />
        <p className={styles.saved}>자동 저장 · 이 기기에만 보관되며 서버로 보내지 않습니다</p>
      </div>
    </div>
  )
}
