import type { EvidenceDetail } from '../../api/types'
import { evidencePhoto } from '../../data/evidenceImages'
import { npcName } from '../../data/characters'
import { useGameStore } from '../../store/gameStore'
import styles from './Evidence.module.css'

// 증거 상세·나란히 보기 공용 부품 (증거 화면, 면담 화면 증거 고르기 창에서 함께 쓴다)

const ROUTE_LABEL: Record<NonNullable<EvidenceDetail['acquiredBy']>, string> = {
  question: '질문으로 확보',
  present: '증거 제시로 확보',
  initial: '현장에서 확보',
}
export const routeLabel = (d: EvidenceDetail) => (d.acquiredBy ? ROUTE_LABEL[d.acquiredBy] : '서버 기록 미제공')

/** 획득 경로·보유 인물 요약 칩 (상세·비교 공용) */
export function EvidenceChips({ detail }: { detail: EvidenceDetail }) {
  return (
    <p className={styles.chips} aria-label="증거 요약">
      <span>{routeLabel(detail)}</span>
      <span>보유 · {npcName(detail.holderId)}</span>
    </p>
  )
}

/** 증거 사진 (상세·비교 공용). 이미지가 없거나 못 불러오면 숨긴다 */
export function EvidencePhotoFigure({ sessionId, id }: { sessionId?: string; id: string }) {
  const ph = evidencePhoto(sessionId, id)
  if (!ph) return null
  return (
    <figure className={styles.prop}>
      <img src={ph.src} alt="" draggable={false} onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = 'none' }} />
      <figcaption>{ph.caption}</figcaption>
    </figure>
  )
}

/** 나란히 보기: 증거 최대 2개를 좌우로(좁으면 위아래로). 차이 강조·자동 메모 없음 */
export function EvidenceCompare({ ids }: { ids: string[] }) {
  const cache = useGameStore((s) => s.evidence)
  const sessionId = useGameStore((s) => s.session?.sessionId)
  return (
    <div className={styles.compare}>
      {ids.map((id) => {
        const d = cache[id]
        return d ? (
          <article key={id} className={`${styles.paper} ${styles.paperCompact}`}>
            <span className={styles.stamp}>{d.id}</span>
            <h2 className="serif">{d.title}</h2>
            <EvidenceChips detail={d} />
            <EvidencePhotoFigure sessionId={sessionId} id={d.id} />
            {(d.documents ?? []).length > 1 ? (
              d.documents!.map((doc) => (
                <section key={doc.id} className={styles.docBlock}>
                  <h3>{doc.label} · {doc.title}</h3>
                  <p className={styles.body}>{doc.body}</p>
                </section>
              ))
            ) : (
              <p className={styles.body}>{d.documents?.[0]?.body ?? d.body ?? '증거 원문은 아직 서버에서 제공되지 않았습니다.'}</p>
            )}
          </article>
        ) : (
          <p key={id} className={styles.empty}>불러오는 중…</p>
        )
      })}
    </div>
  )
}
