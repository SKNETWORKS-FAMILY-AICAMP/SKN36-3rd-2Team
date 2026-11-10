// 표시 이름·직함·이미지 경로를 한 곳에서 관리한다 (앨범 이름 매핑 변경 지점).
// 공개 정보(이름, 2026년 직함)만 담는다. 비공개 지식·행적은 넣지 않는다.

export type CharacterId =
  | 'C01' | 'C02' | 'C03' | 'C04' | 'C05'
  | 'C06' | 'C07' | 'C08' | 'C09' | 'C10'

export type AlbumId = CharacterId | 'V01' | 'M01'

export interface AlbumEntry {
  id: AlbumId
  name: string
  /** 앨범 타일 이미지 (재생성본이 오면 파일만 교체) */
  tile: string
  /** 앨범에서 강조 프레임 */
  highlight?: boolean
}

const asset = (p: string) => `${import.meta.env.BASE_URL}assets/${p}`

// 앨범 배치 순서: 1행 6명, 2행 6명
export const ALBUM: AlbumEntry[] = [
  { id: 'V01', name: '신기범', tile: asset('album/V01.webp') },
  { id: 'C01', name: '윤태식', tile: asset('album/C01.webp') },
  { id: 'C07', name: '장현우', tile: asset('album/C07.webp') },
  { id: 'C08', name: '서미란', tile: asset('album/C08.webp') },
  { id: 'C09', name: '후지이 류', tile: asset('album/C09.webp') },
  { id: 'C06', name: '주청', tile: asset('album/C06.webp') },
  { id: 'C03', name: '박도현', tile: asset('album/C03.webp') },
  { id: 'C02', name: '문지혜', tile: asset('album/C02.webp') },
  { id: 'C04', name: '최민석', tile: asset('album/C04.webp') },
  { id: 'C05', name: '정유라', tile: asset('album/C05.webp') },
  { id: 'C10', name: '오재민', tile: asset('album/C10.webp') },
  { id: 'M01', name: '백서윤', tile: asset('album/M01.webp'), highlight: true },
]

export const GROUP_PHOTO = asset('group/group2016.webp')
export const POSTER_BG = asset('backgrounds/bg_poster.webp')

// ── NPC 공개 프로필 (대화 화면용) ─────────────────────────────
// 직함/외형/말투는 공개 가능한 첫 문장 수준만 담는다. 행적·비밀·관계는 넣지 않는다.
export interface NpcPublic {
  id: CharacterId
  name: string
  title: string
  age: string
  look: string
  tone: string
}

export const NPC_PUBLIC: NpcPublic[] = [
  { id: 'C01', name: '윤태식', title: '재단 이사장', age: '50대 초반', look: '단정한 정장, 흐트러짐 없는 자세', tone: '침착한 정중체' },
  { id: 'C02', name: '문지혜', title: '자산운용 실무 책임자', age: '20대 후반', look: '정교한 인상, 날카로운 눈매, 단정한 비즈니스 복장', tone: '짧고 통제된 문장' },
  { id: 'C03', name: '박도현', title: '부동산·시설운영사 후계자', age: '20대 후반', look: '활동하기 편한 복장, 실무자 느낌', tone: '실무적인 말투' },
  { id: 'C04', name: '최민석', title: '사이버보안기업 공동창업자 · 행사 보안 총괄', age: '20대 후반', look: '말끔한 셔츠, 무표정', tone: '단답형' },
  { id: 'C05', name: '정유라', title: '의사 (수련의)', age: '20대 후반', look: '차분한 인상, 정돈된 복장', tone: '침착한 의료인 어투' },
  { id: 'C06', name: '주청', title: '상하이 투자회사 전략담당', age: '20대 후반', look: '단정한 차림, 조용한 인상', tone: '정중한 한국어' },
  { id: 'C07', name: '장현우', title: '물류·전시업체 후계자', age: '20대 후반', look: '밝은 인상, 가벼운 복장', tone: '붙임성 있는 존댓말' },
  { id: 'C08', name: '서미란', title: '교육 컨설팅기업 대표 · 전 교직원', age: '40대 중반', look: '깔끔한 정장, 절제된 표정', tone: '마른 냉소의 존댓말' },
  { id: 'C09', name: '후지이 류', title: '미디어그룹 후계자 · 제작자', age: '20대 후반', look: '카메라를 든 모습이 어울리는 인상', tone: '조심스러운 정중체' },
  { id: 'C10', name: '오재민', title: '데이터 감사 스타트업 대표', age: '20대 후반', look: '캐주얼한 차림, 분주한 인상', tone: '빠른 말투' },
]

export const npcName = (id: string) =>
  ALBUM.find((a) => a.id === id)?.name ?? id

export const npcTile = (id: string) =>
  ALBUM.find((a) => a.id === id)?.tile ?? ''

/** 인물 입상(차분) 이미지. 아직 없으면 컴포넌트가 앨범 타일로 대체한다. */
export const npcPortrait = (id: string) => asset(`characters/${id}_calm.webp`)

/** 관계도 보드의 핀 위치(%). 관계를 암시하지 않도록 고르게 흩어 둔 배치. */
export const BOARD_POS: Record<CharacterId | 'V01', { x: number; y: number; tilt: number }> = {
  V01: { x: 50, y: 54, tilt: 0 },
  C01: { x: 14, y: 12, tilt: -3 },
  C02: { x: 38, y: 6, tilt: 2 },
  C03: { x: 64, y: 14, tilt: -2 },
  C04: { x: 86, y: 8, tilt: 3 },
  C05: { x: 24, y: 40, tilt: 2 },
  C06: { x: 50, y: 34, tilt: -3 },
  C07: { x: 76, y: 42, tilt: 2 },
  C08: { x: 12, y: 68, tilt: -2 },
  C09: { x: 42, y: 66, tilt: 3 },
  C10: { x: 70, y: 70, tilt: -3 },
}
