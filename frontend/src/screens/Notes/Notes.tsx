import TopNav from '../../components/TopNav'
import Notebook from '../../components/Notebook'
import styles from './Notes.module.css'

export default function Notes() {
  return (
    <div className={styles.page}>
      <TopNav />
      <main className={styles.main}>
        <header className={`${styles.head} page-head`}>
          <h1 className="serif">수사관의 추리 노트</h1>
          <p>CASE 001 · 플레이어 개인 기록 — 직접 쓰는 노트입니다. 정답 판정과는 관계없습니다.</p>
        </header>
        <div className={styles.book}><Notebook /></div>
      </main>
    </div>
  )
}
