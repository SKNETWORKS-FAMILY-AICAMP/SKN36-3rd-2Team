// 공개 배경/확대 이미지와 화면 배치만 관리합니다.
// 이 ID는 프론트 화면용이며 서버 증거/해금 ID가 아닙니다.
export interface FieldAction {
  id: string
  label: string
}

export interface Hotspot {
  id: string
  label: string
  x: number
  y: number
  zoom?: string
  subview?: string
  actions?: FieldAction[]
}

export interface FieldScene {
  id: string
  name: string
  floor: string
  image: string
  hotspots: Hotspot[]
}

export const fieldPlaces: FieldScene[] = [
  { id: 'lobby', name: '1층 로비', floor: '1층', image: 'bg_lobby.webp', hotspots: [
    { id: 'sample-poster', label: '행사 포스터', x: 86, y: 42, zoom: 'lobby_poster.png' },
    { id: 'sample-desk', label: '안내데스크', x: 75, y: 66, subview: 'desk' },
    { id: 'sample-corridor', label: '복도 둘러보기', x: 48, y: 52, subview: 'corridor' },
  ] },
  { id: 'stairs', name: '내부 계단', floor: '1층 ↔ 2층', image: 'bg_stairs.webp', hotspots: [
    { id: 'sample-rail', label: '계단 난간', x: 55, y: 58, zoom: 'stairs_rail.png', actions: [{ id: 'inspect-sensor-record', label: '시설 센서 기록 조회' }] },
    { id: 'sample-wall', label: '벽면 안내', x: 91, y: 34, zoom: 'stairs_sign.png' },
  ] },
  { id: 'records', name: '2층 기록실', floor: '2층', image: 'bg_records.webp', hotspots: [
    { id: 'sample-shelf', label: '문서 보관함', x: 23, y: 45, zoom: 'records_shelf.png', actions: [{ id: 'inspect-e13-a', label: '재단 기록 열람' }] },
    { id: 'sample-cabinet', label: '행정 자료 보관 구역', x: 72, y: 60, subview: 'admin' },
  ] },
  { id: 'office', name: '신기범 사무실', floor: '2층', image: 'bg_office.webp', hotspots: [
    { id: 'sample-drawer', label: '책상 서랍', x: 37, y: 79, zoom: 'office_drawer.png' },
    { id: 'sample-pc', label: '컴퓨터 화면', x: 59, y: 59, zoom: 'office_pc.png', actions: [{ id: 'inspect-e20-a', label: '사무실 자료 조사' }] },
  ] },
  { id: 'security', name: '보안 통제실', floor: '1층', image: 'bg_security.png', hotspots: [
    { id: 'sample-screen', label: '관제 모니터', x: 36, y: 34, zoom: 'security_monitor.png', actions: [{ id: 'inspect-emergency-door-record', label: '비상문 기록 조회' }] },
    { id: 'sample-exit', label: '비상문 시설', x: 15, y: 60, subview: 'exit' },
  ] },
  { id: 'album', name: '옛 교실·졸업앨범실', floor: '1층', image: 'bg_albumroom.png', hotspots: [
    { id: 'sample-album', label: '앨범 보관함', x: 17, y: 35, zoom: 'album_cabinet.png', actions: [{ id: 'inspect-e11-a', label: '앨범 원본 조사' }] },
    { id: 'sample-student', label: '학생회 자료 구역', x: 68, y: 58, subview: 'student' },
  ] },
  { id: 'counsel', name: '상담실', floor: '1층', image: 'bg_counsel.png', hotspots: [
    { id: 'sample-box', label: '자료 보관함', x: 13, y: 39, zoom: 'counsel_cabinet.png' },
  ] },
]

export const fieldSubviews: Record<string, FieldScene> = {
  desk: { id: 'desk', name: '안내데스크', floor: '1층', image: 'bg_desk.png', hotspots: [
    { id: 'sample-ledger', label: '접수대 문서', x: 51, y: 66, zoom: 'desk_ledger.png', actions: [{ id: 'inspect-e19-a', label: '접수 기록 조사' }, { id: 'inspect-e21-a', label: '출입카드 기록 조사' }] },
  ] },
  corridor: { id: 'corridor', name: '1층 복도', floor: '1층', image: 'bg_corridor.png', hotspots: [
    { id: 'sample-window', label: '유리창', x: 76, y: 42, zoom: 'corridor_glass.png' },
  ] },
  admin: { id: 'admin', name: '행정 자료 보관 구역', floor: '2층', image: 'bg_admin.png', hotspots: [
    { id: 'sample-admin-box', label: '문서함', x: 57, y: 65, zoom: 'admin_box.png', actions: [{ id: 'inspect-e14-a', label: '학적 관련 기록 조사' }] },
  ] },
  student: { id: 'student', name: '학생회 자료 구역', floor: '1층', image: 'bg_council.png', hotspots: [
    { id: 'sample-student-box', label: '보관함', x: 42, y: 54, zoom: 'council_box.png', actions: [{ id: 'inspect-e12-a', label: '학생회 회람 자료 조사' }] },
  ] },
  exit: { id: 'exit', name: '북측 비상계단', floor: '2층', image: 'bg_emergency.png', hotspots: [
    { id: 'sample-exit-sign', label: '안내 표지', x: 48, y: 21, zoom: 'exit_sign.png' },
  ] },
}

export interface MapRoom {
  name: string
  image: string
  place?: string
  description?: string
  rect: [number, number, number, number]
}
export const floorMaps: { name: string; rooms: MapRoom[] }[] = [
  { name: '1층', rooms: [
    { name: '행사장', image: 'bg_hall.png', description: '동창회 장소 · 구조 안내', rect: [3, 9, 73, 28] },
    { name: '옛 교실 자료실', image: 'bg_albumroom.png', place: 'album', rect: [3, 39, 35, 15] },
    { name: '상담실', image: 'bg_counsel.png', place: 'counsel', rect: [41, 39, 35, 15] },
    { name: '계단', image: 'bg_stairs.webp', place: 'stairs', rect: [79, 9, 18, 43] },
    { name: '엘리베이터', image: 'bg_elevator.png', description: '층간 이동 시설', rect: [79, 54, 18, 14] },
    { name: '로비', image: 'bg_lobby.webp', place: 'lobby', rect: [3, 56, 73, 22] },
    { name: '경비실', image: 'bg_security.png', place: 'security', rect: [3, 80, 21, 16] },
    { name: '안내데스크', image: 'bg_desk.png', description: '로비에서 살펴볼 수 있는 세부 공간', rect: [26, 80, 20, 16] },
    { name: '후문', image: 'bg_backdoor.png', description: '구조 안내', rect: [79, 80, 18, 16] },
  ] },
  { name: '2층', rooms: [
    { name: '신기범 사무실', image: 'bg_office.webp', place: 'office', rect: [3, 9, 32, 40] },
    { name: '기록실', image: 'bg_records.webp', place: 'records', rect: [37, 9, 35, 26] },
    { name: '계단', image: 'bg_stairs.webp', place: 'stairs', rect: [75, 9, 22, 41] },
    { name: '면담실', image: 'bg_meeting.png', place: 'interview', rect: [37, 38, 35, 26] },
    { name: '비품실', image: 'bg_supply.png', description: '구조 안내', rect: [3, 52, 32, 20] },
    { name: '엘리베이터', image: 'bg_elevator.png', description: '층간 이동 시설', rect: [75, 53, 22, 17] },
    { name: '비상계단', image: 'bg_emergency.png', description: '보안 통제실의 비상문 시설과 관련된 구조', rect: [3, 75, 32, 21] },
    { name: '화장실', image: 'bg_restroom.png', description: '구조 안내', rect: [37, 67, 35, 29] },
  ] },
  { name: '지하층', rooms: [
    { name: '창고', image: 'bg_storage.png', description: '일반 출입 불가 · 구조 안내', rect: [6, 12, 88, 48] },
    { name: '설비실', image: 'bg_utility.png', description: '일반 출입 불가 · 구조 안내', rect: [6, 63, 88, 33] },
  ] },
]

export const backgroundUrl = (file: string) => `${import.meta.env.BASE_URL}assets/backgrounds/${file}`
export const zoomUrl = (file: string) => `${import.meta.env.BASE_URL}assets/zoom/${file}`
