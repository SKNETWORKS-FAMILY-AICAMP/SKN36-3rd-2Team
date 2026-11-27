import { useState } from 'react'
import { useNoteStore } from '../../store/noteStore'
import type { EmbedProps } from '../embed'
import styles from './Timeline.module.css'

/**
 * 플레이어가 알게 된 사실 한 줄. 서버 GET /timeline(11/30 예정)이 내려 주는 항목만 그린다.
 * 응답 스키마가 오면 필드 이름을 맞춘다. 배열 순서 = 발견 순.
 */
export interface TimelineItem {
  id: string
  /** 사건 시각(예: 21:25). 없으면 시각 순에서 맨 뒤 */
  time?: string
  text: string
  /** 최근에 새로 알게 된 항목 */
  isNew?: boolean
}

type Order = 'found' | 'time'

const byTime = (a: TimelineItem, b: TimelineItem) =>
  a.time && b.time ? a.time.localeCompare(b.time) : a.time ? -1 : b.time ? 1 : 0

/** 발견 순/시각 순 전환, 「새로 알게 됨」, 플레이어가 직접 하는 모순 표시 */
export function TimelineList({ items }: { items: TimelineItem[] }) {
  const [order, setOrder] = useState<Order>('found')
  const marks = useNoteStore((s) => s.marks)
  const toggleMark = useNoteStore((s) => s.toggleMark)
  const shown = order === 'time' ? [...items].sort(byTime) : items

  return (
    <>
      <div className={styles.order} role="group" aria-label="정렬">
        {(['found', 'time'] as const).map((o) => (
          <button key={o} type="button" aria-pressed={order === o} onClick={() => setOrder(o)}>
            {o === 'found' ? '발견 순' : '시각 순'}
          </button>
        ))}
      </div>
      <ol className={styles.list}>
        {shown.map((item) => {
          const marked = marks.includes(item.id)
          return (
            <li key={item.id} className={marked ? styles.marked : undefined}>
              <span className={styles.time}>{item.time ?? '시각 미상'}</span>
              <p>
                {item.isNew && <em className={styles.new}>새로 알게 됨</em>}
                {item.text}
              </p>
              <button type="button" className={styles.mark} aria-pressed={marked} onClick={() => toggleMark(item.id)}>
                {marked ? '모순 표시 해제' : '모순 표시'}
              </button>
            </li>
          )
        })}
      </ol>
    </>
  )
}

export default function Timeline({ embedded = false }: EmbedProps = {}) {
  // GET /timeline 연결 전(11/30 예정)에는 항목이 없다. 연결 뒤 서버 응답을 TimelineList에 넘긴다.
  const items: TimelineItem[] | null = null

  return (
    <section className={`${styles.page} ${embedded ? styles.embedded : ''}`} aria-label="타임라인">
      <h2 className={styles.title}>타임라인</h2>
      {items
        ? <TimelineList items={items} />
        : <p className={styles.empty} role="status">서버 준비 중입니다. 알게 된 사실이 생기면 여기에 순서대로 쌓입니다.</p>}
    </section>
  )
}
