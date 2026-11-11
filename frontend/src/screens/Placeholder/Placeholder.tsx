import { Link } from 'react-router-dom'

const ROUTES = [
  ['/story', '스토리'],
  ['/chat', 'NPC 대화'],
  ['/evidence', '증거 보관함'],
  ['/relations', '인물 관계도'],
  ['/accuse', '범인 지목'],
] as const

// 아직 만들지 않은 화면의 자리. 단계별로 실제 화면으로 교체한다.
export default function Placeholder({ title }: { title: string }) {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center' }}>
      <div>
        <h1 className="serif" style={{ fontSize: 32, color: 'var(--brass-400)', letterSpacing: '0.1em' }}>{title}</h1>
        <p style={{ margin: '12px 0 28px', color: 'var(--paper-400)' }}>이 화면은 다음 단계에서 제작합니다.</p>
        <nav style={{ display: 'flex', gap: 14, flexWrap: 'wrap', justifyContent: 'center' }}>
          <Link to="/" style={{ color: 'var(--paper-200)' }}>메인</Link>
          {ROUTES.map(([to, label]) => (
            <Link key={to} to={to} style={{ color: 'var(--paper-300)' }}>{label}</Link>
          ))}
        </nav>
      </div>
    </main>
  )
}
