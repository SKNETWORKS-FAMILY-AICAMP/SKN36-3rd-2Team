import { useState } from 'react'
import { POSTER_BG } from '../data/characters'
import RainCanvas from './RainCanvas'
import styles from './PosterScene.module.css'

// 임시 배경: bg_poster.webp 가 public/assets/backgrounds/ 에 들어오면 그 이미지가 위에 덮인다.
const WINDOW_COLS_MAIN = [610, 680, 750, 820, 1050, 1120, 1190, 1260]
const WINDOW_COLS_WING_L = [300, 370, 440, 500]
const WINDOW_COLS_WING_R = [1420, 1480, 1550, 1610]

const isLit = (i: number, j: number, k: number) => (i * 7 + j * 5 + k * 3) % 11 < 3

function Building() {
  const win = (x: number, y: number, key: string, lit: boolean, flick: boolean) => (
    <rect
      key={key}
      x={x}
      y={y}
      width={34}
      height={58}
      rx={2}
      className={lit ? (flick ? styles.winFlicker : styles.winLit) : styles.winDark}
    />
  )
  const wins: JSX.Element[] = []
  ;[480, 600].forEach((y, j) =>
    WINDOW_COLS_MAIN.forEach((x, i) => wins.push(win(x, y, `m${i}-${j}`, isLit(i, j, 1), i === 2 && j === 1))),
  )
  ;[565, 665].forEach((y, j) => {
    WINDOW_COLS_WING_L.forEach((x, i) => wins.push(win(x, y, `l${i}-${j}`, isLit(i, j, 2), false)))
    WINDOW_COLS_WING_R.forEach((x, i) => wins.push(win(x, y, `r${i}-${j}`, isLit(i, j, 3), i === 1 && j === 0)))
  })

  return (
    <g>
      {/* 날개 건물 */}
      <rect x={250} y={520} width={330} height={240} fill="#0d1013" />
      <rect x={1340} y={520} width={330} height={240} fill="#0d1013" />
      <rect x={250} y={505} width={330} height={16} fill="#14181c" />
      <rect x={1340} y={505} width={330} height={16} fill="#14181c" />
      {/* 본관 */}
      <rect x={560} y={420} width={800} height={340} fill="#101317" />
      <polygon points="540,424 960,330 1380,424" fill="#0b0d10" />
      <rect x={540} y={420} width={840} height={14} fill="#161b20" />
      {/* 시계탑 */}
      <rect x={895} y={190} width={130} height={240} fill="#0f1215" />
      <polygon points="880,196 960,80 1040,196" fill="#0a0c0e" />
      <circle cx={960} cy={262} r={30} fill="#1c2329" stroke="#2c353c" strokeWidth={3} />
      <circle cx={960} cy={262} r={22} fill="none" stroke="#7d8a8f" strokeWidth={1.5} opacity={0.5} />
      <line x1={960} y1={262} x2={960} y2={246} stroke="#9aa6aa" strokeWidth={2} opacity={0.7} />
      <line x1={960} y1={262} x2={972} y2={268} stroke="#9aa6aa" strokeWidth={2} opacity={0.7} />
      {/* 현관 아치 */}
      <path d="M918 760 V650 a42 42 0 0 1 84 0 V760 Z" fill="#1a1308" />
      <path d="M926 760 V652 a34 34 0 0 1 68 0 V760 Z" className={styles.doorGlow} />
      {wins}
    </g>
  )
}

export default function PosterScene() {
  const [imgOk, setImgOk] = useState(true)
  return (
    <div className={styles.scene} aria-hidden="true">
      <svg className={styles.svg} viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#05070a" />
            <stop offset="0.55" stopColor="#111820" />
            <stop offset="1" stopColor="#1b242b" />
          </linearGradient>
          <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#12171b" />
            <stop offset="1" stopColor="#050607" />
          </linearGradient>
          <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fff" stopOpacity="0.5" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
          <mask id="reflMask">
            <rect x="0" y="760" width="1920" height="320" fill="url(#fade)" />
          </mask>
          <filter id="blur6"><feGaussianBlur stdDeviation="5" /></filter>
          <radialGradient id="cloud" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stopColor="#2a343c" stopOpacity="0.55" />
            <stop offset="1" stopColor="#2a343c" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="1920" height="1080" fill="url(#sky)" />
        <ellipse cx="480" cy="170" rx="520" ry="130" fill="url(#cloud)" />
        <ellipse cx="1480" cy="120" rx="620" ry="150" fill="url(#cloud)" />
        <ellipse cx="960" cy="40" rx="760" ry="110" fill="url(#cloud)" />
        <Building />
        <rect x="0" y="760" width="1920" height="320" fill="url(#ground)" />
        <g mask="url(#reflMask)" filter="url(#blur6)" opacity="0.8">
          <g transform="translate(0 1520) scale(1 -1)"><Building /></g>
        </g>
      </svg>
      {imgOk && (
        <img
          className={styles.photo}
          src={POSTER_BG}
          alt=""
          onError={() => setImgOk(false)}
        />
      )}
      <RainCanvas />
      <div className={styles.flash} />
      <div className={styles.shade} />
    </div>
  )
}
