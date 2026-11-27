import { useState } from 'react'
import { NOTE_SECTIONS, useNoteStore } from '../store/noteStore'
import { npcName } from '../data/characters'
import styles from './Notebook.module.css'

// 직접 쓰는 빈 노트. 시스템이 내용을 채우지 않는다. 항목은 "나만의 추리" 하나뿐이다.
export default function Notebook({ compact = false }: { compact?: boolean }) {
  const notes = useNoteStore((s) => s.notes)
  const setNote = useNoteStore((s) => s.setNote)
  const statements = useNoteStore((s) => s.statements)
  const toggleStatement = useNoteStore((s) => s.toggleStatement)
  const section = NOTE_SECTIONS[0]
  // 진술 대조: 저장한 진술을 2개까지 골라 나란히 본다(증거 나란히 보기와 같은 방식, 차이 강조 없음)
  const [comparing, setComparing] = useState(false)
  const [picks, setPicks] = useState<string[]>([])
  const pickedList = picks.map((id) => statements.find((s) => s.id === id)).filter((s) => s !== undefined)
  const toggleCompare = () => { setComparing((on) => !on); setPicks([]) }
  const togglePick = (id: string) => setPicks((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length < 2 ? [...cur, id] : cur))

  return (
    <div className={`${styles.book} ${compact ? styles.compact : ''}`}>
      <div className={styles.page}>
        <div className={styles.head}>
          <h3 className="serif">저장한 진술</h3>
          <button type="button" className={styles.cmpBtn} aria-pressed={comparing} disabled={!comparing && statements.length < 2} title={statements.length < 2 ? '진술을 2개 이상 저장하면 대조할 수 있습니다.' : undefined} onClick={toggleCompare}>
            {comparing ? '대조 끝내기' : '진술 대조'}
          </button>
        </div>
        {comparing && <p className={styles.empty} aria-live="polite">대조할 진술을 2개까지 고르세요 · {picks.length} / 2</p>}
        {statements.length === 0 ? (
          <p className={styles.empty}>면담 중 인물 답변의 「진술 저장」(통합 화면에서는 답변에 마우스를 올리면 나오는 핀)을 누르면 여기에 모입니다.</p>
        ) : (
          <ul className={styles.statements}>
            {statements.map((s) => (
              <li key={s.id}>
                {comparing && (
                  <button type="button" className={styles.pick} aria-pressed={picks.includes(s.id)} disabled={!picks.includes(s.id) && picks.length >= 2} onClick={() => togglePick(s.id)} aria-label={`${npcName(s.npcId)} 진술 대조에 ${picks.includes(s.id) ? '빼기' : '넣기'}`}>
                    {picks.includes(s.id) ? picks.indexOf(s.id) + 1 : ''}
                  </button>
                )}
                <b>{npcName(s.npcId)}</b>
                <span>{s.text}</span>
                {!comparing && <button type="button" onClick={() => toggleStatement(s)} aria-label={`${npcName(s.npcId)} 진술 삭제`}>삭제</button>}
              </li>
            ))}
          </ul>
        )}
        {comparing && pickedList.length === 2 && (
          <div className={styles.compare} aria-label="진술 대조">
            {pickedList.map((s) => (
              <article key={s.id}>
                <b>{npcName(s.npcId)}</b>
                <p>{s.text}</p>
              </article>
            ))}
          </div>
        )}
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
