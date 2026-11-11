import { NOTE_SECTIONS, useNoteStore } from '../store/noteStore'
import styles from './Notebook.module.css'

// 직접 쓰는 빈 노트. 시스템이 내용을 채우지 않는다. 항목은 "나만의 추리" 하나뿐이다.
export default function Notebook({ compact = false }: { compact?: boolean }) {
  const notes = useNoteStore((s) => s.notes)
  const setNote = useNoteStore((s) => s.setNote)
  const section = NOTE_SECTIONS[0]

  return (
    <div className={`${styles.book} ${compact ? styles.compact : ''}`}>
      <div className={styles.page}>
        <h3 className="serif">{section.title}</h3>
        <textarea
          value={notes.theory}
          placeholder={section.hint}
          onChange={(e) => setNote('theory', e.target.value)}
          spellCheck={false}
          aria-label={section.title}
        />
        <p className={styles.saved}>자동 저장 · 이 기기에만 보관되며 서버로 보내지 않습니다</p>
      </div>
    </div>
  )
}
