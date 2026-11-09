import type { ReactElement } from 'react'
import styles from './PlaceScene.module.css'

export type PlaceKey = 'lobby' | 'stairs' | 'records' | 'office'

// 이미지 파일 없이 그린 장소 배경. 사진 배경이 준비되면 같은 자리에 교체한다.
const SCENES: Record<PlaceKey, ReactElement> = {
  lobby: (
    <>
      <defs>
        <linearGradient id="lb-wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#14110e" /><stop offset="1" stopColor="#0b0a09" />
        </linearGradient>
        <radialGradient id="lb-door" cx="0.5" cy="0.6" r="0.7">
          <stop offset="0" stopColor="#d9a860" stopOpacity="0.55" /><stop offset="1" stopColor="#d9a860" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#lb-wall)" />
      <rect y="640" width="1600" height="260" fill="#0a0807" />
      <ellipse cx="800" cy="560" rx="520" ry="360" fill="url(#lb-door)" />
      <path d="M690 250h220a110 110 0 0 1 110 110v360H580V360a110 110 0 0 1 110-110z" fill="#1d1510" stroke="#3a2a1a" strokeWidth="6" />
      <path d="M700 270h200a90 90 0 0 1 90 90v350H610V360a90 90 0 0 1 90-90z" fill="#3a2a16" opacity="0.8" />
      <line x1="800" y1="270" x2="800" y2="710" stroke="#120d09" strokeWidth="6" />
      {[200, 340, 1260, 1400].map((x) => (
        <g key={x}><rect x={x - 40} y="180" width="80" height="460" fill="#100d0b" /><rect x={x - 46} y="170" width="92" height="16" fill="#1c1612" /></g>
      ))}
      <rect x="1000" y="610" width="420" height="40" fill="#1a1410" />
      <rect x="1010" y="650" width="400" height="60" fill="#0e0b09" />
      <rect x="170" y="640" width="220" height="30" fill="#17120e" />
      <path d="M800 0v110" stroke="#2a2018" strokeWidth="4" /><circle cx="800" cy="124" r="22" fill="#8a6a38" opacity="0.5" />
    </>
  ),
  stairs: (
    <>
      <defs>
        <linearGradient id="st-bg" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#0c1218" /><stop offset="1" stopColor="#090b0d" />
        </linearGradient>
        <linearGradient id="st-win" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7ea1b8" stopOpacity="0.55" /><stop offset="1" stopColor="#7ea1b8" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#st-bg)" />
      <path d="M1180 120h250v420h-250z" fill="#a9c2d2" opacity="0.18" />
      <path d="M1180 540L560 900h1040z" fill="url(#st-win)" opacity="0.35" />
      <path d="M0 900V760L180 760V690L360 690V620L540 620V550L720 550V480L900 480V410L1080 410V340L1260 340V270H1600V900z" fill="#10151a" />
      <path d="M180 760H360M360 690H540M540 620H720M720 550H900M900 480H1080M1080 410H1260M1260 340H1600" stroke="#2a323a" strokeWidth="6" />
      <path d="M0 900V760" stroke="#05070a" strokeWidth="2" />
      <path d="M180 650L1260 230" stroke="#2f3840" strokeWidth="9" />
      {[250, 430, 610, 790, 970, 1150].map((x, i) => <line key={x} x1={x} y1={640 - i * 70} x2={x} y2={738 - i * 70 + 10} stroke="#2f3840" strokeWidth="6" />)}
      <path d="M200 700L1180 300" stroke="#c9a45f" strokeWidth="4" strokeDasharray="22 14" opacity="0.7" />
    </>
  ),
  records: (
    <>
      <defs>
        <radialGradient id="rc-lamp" cx="0.3" cy="0.55" r="0.55">
          <stop offset="0" stopColor="#e0b46a" stopOpacity="0.5" /><stop offset="1" stopColor="#e0b46a" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="1600" height="900" fill="#0d0b09" />
      {[0, 1, 2].map((s) => (
        <g key={s}>
          <rect x={700 + s * 300} y="90" width="260" height="660" fill="#17110c" stroke="#2c2016" strokeWidth="4" />
          {[0, 1, 2, 3, 4].map((r) => (
            <g key={r}>
              <rect x={708 + s * 300} y={170 + r * 120} width="244" height="8" fill="#2c2016" />
              {Array.from({ length: 7 }, (_, k) => (
                <rect key={k} x={716 + s * 300 + k * 33} y={110 + r * 120 + ((k * 7 + r * 3) % 4) * 4} width="24" height={56 - ((k * 7 + r * 3) % 4) * 4} fill={['#3a2a1c', '#2a2218', '#41311f', '#241b14'][(k + r) % 4]} />
              ))}
            </g>
          ))}
        </g>
      ))}
      <rect x="120" y="580" width="520" height="30" fill="#2a1e14" /><rect x="150" y="610" width="30" height="190" fill="#1d150e" /><rect x="580" y="610" width="30" height="190" fill="#1d150e" />
      <rect x="300" y="560" width="120" height="20" fill="#1b1410" /><rect x="470" y="520" width="8" height="60" fill="#3a2a1a" /><path d="M440 520h70l-20-36h-30z" fill="#5a4426" />
      <rect width="1600" height="900" fill="url(#rc-lamp)" />
    </>
  ),
  office: (
    <>
      <defs>
        <linearGradient id="of-win" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1c2a36" /><stop offset="1" stopColor="#0d141b" />
        </linearGradient>
        <radialGradient id="of-lamp" cx="0.5" cy="0.6" r="0.5">
          <stop offset="0" stopColor="#e0b46a" stopOpacity="0.42" /><stop offset="1" stopColor="#e0b46a" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="1600" height="900" fill="#0e0c0a" />
      <rect x="980" y="120" width="480" height="420" fill="url(#of-win)" stroke="#2a2018" strokeWidth="10" />
      <line x1="1220" y1="120" x2="1220" y2="540" stroke="#2a2018" strokeWidth="8" />
      {Array.from({ length: 16 }, (_, i) => <line key={i} className={styles.drop} x1={1000 + i * 28} y1="130" x2={992 + i * 28} y2="200" stroke="#7ea1b8" strokeWidth="2" opacity="0.5" style={{ animationDelay: `${(i * 0.37) % 2}s` }} />)}
      <rect x="260" y="560" width="760" height="40" fill="#2a1e14" /><rect x="290" y="600" width="260" height="260" fill="#1a1410" /><rect x="740" y="600" width="250" height="260" fill="#1a1410" />
      <rect x="340" y="650" width="160" height="14" fill="#2f2318" /><rect x="790" y="650" width="150" height="14" fill="#2f2318" />
      <rect x="620" y="500" width="120" height="14" fill="#3a2a1a" /><rect x="480" y="508" width="70" height="52" fill="#d8cdb4" opacity="0.65" />
      <rect x="1070" y="430" width="30" height="130" fill="#17120e" /><path d="M560 380h150l-24-40h-102z" fill="#5a4426" /><rect x="630" y="380" width="8" height="180" fill="#3a2a1a" />
      <path d="M1180 560c0-90 110-130 160-60l60 60z" fill="#120e0b" />
      <rect width="1600" height="900" fill="url(#of-lamp)" />
    </>
  ),
}

export default function PlaceScene({ place }: { place: PlaceKey }) {
  return (
    <svg className={styles.scene} viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" role="img" aria-label="장소 배경">
      {SCENES[place]}
      {place === 'records' && Array.from({ length: 24 }, (_, i) => (
        <circle key={i} className={styles.dust} cx={160 + ((i * 197) % 1280)} cy={140 + ((i * 113) % 620)} r={1.5 + (i % 3)} fill="#e0c690" opacity="0.5" style={{ animationDelay: `${(i * 0.5) % 6}s` }} />
      ))}
    </svg>
  )
}
