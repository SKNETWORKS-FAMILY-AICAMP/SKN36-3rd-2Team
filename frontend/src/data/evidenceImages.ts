/**
 * CASE-001 증거 사진 연결
 * 현재 게임 프론트엔드의 evidencePhoto(sessionId, evidenceId) 인터페이스를 유지합니다.
 * 사진은 획득된 증거에 대해서만 화면에 렌더링되지만, 정적 파일 URL 자체는 공개됩니다.
 */
type EvidencePhoto = { src: string; thumb: string; caption: string }

const evidenceAssets: Readonly<Record<string, { file: string; caption: string }>> = {
  E01: { file: 'd01', caption: '확보 자료 사본' },
  E02: { file: 'p1', caption: '현장 촬영본' },
  E03: { file: 'd03', caption: '확보 자료 사본' },
  E04: { file: 'd04', caption: '확보 자료 사본' },
  E05: { file: 'd05', caption: '확보 자료 사본' },
  E06: { file: 'd06', caption: '확보 자료 사본' },
  E07: { file: 'd07', caption: '확보 자료 사본' },
  E08: { file: 'd08', caption: '확보 자료 사본' },
  E09: { file: 'p2', caption: '현장 촬영본' },
  E10: { file: 'p3', caption: '현장 촬영본' },
}

const base = import.meta.env.BASE_URL
// Vite base './'를 사용하는 경우에도 BrowserRouter 경로 아래에서 자산을 정상 로드합니다.
const assetBase = base.startsWith('.') ? '/' : base.endsWith('/') ? base : `${base}/`
const asset = (filename: string) => `${assetBase}assets/evidence/${filename}.webp`

export function evidencePhoto(sessionId: string | undefined, id: string): EvidencePhoto | undefined {
  if (!sessionId) return undefined
  const photo = evidenceAssets[id]
  if (!photo) return undefined
  return {
    src: asset(photo.file),
    thumb: asset(`t_${photo.file}`),
    caption: photo.caption,
  }
}
