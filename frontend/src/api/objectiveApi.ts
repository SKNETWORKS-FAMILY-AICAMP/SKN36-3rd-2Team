import { request } from './httpApi'

export interface ObjectiveItem {
  objectiveId: string
  status: string
}

export async function getObjectives(sessionId: string): Promise<ObjectiveItem[]> {
  const response = await request<{ items: ObjectiveItem[] }>(
    `/games/${encodeURIComponent(sessionId)}/objectives`,
  )
  return response.items
}

// 콘텐츠 문서의 플레이어용 목표 문구만 사용합니다.
// 목표 해금 및 완료 여부는 서버 응답으로만 결정합니다.
const labels: Record<string, string> = {
  "OBJ_001": "계단·기록실·사무실 세 지점 모두 조사",
  "OBJ_002": "사진 원본을 보관한 사람을 찾기",
  "OBJ_010": "2016년 명단 원본 찾기",
  "OBJ_011": "CCTV 공백의 이유 조사",
  "OBJ_024": "상담실과 영상 기록 대조",
  "OBJ_FIND_STUDENT_RECORD": "학생회 회람 문서(E12)를 찾아 지워진 이름의 학생 기록을 확인",
  "OBJ_CHECK_SCHOLARSHIP": "장학금 수령 명단 원본(E13)을 찾아 회람의 금액과 대조",
  "OBJ_CHECK_SIGNOFF": "학적 변경 승인서(E14)의 서명과 날짜 확인",
  "OBJ_TALK_SEOMIRAN": "서미란에게 2016년 학적 변경 경위를 확인",
  "OBJ_CHECK_2016_VIDEO": "2016년 촬영 영상(E16) 원본 찾기",
  "OBJ_VERIFY_DEPARTURE": "전학 관련 우편 접수증(E18)으로 이탈 경위 확인",
  "OBJ_LINK_2016_2026": "2016 지급 코드와 2026 회계 원본(E27)을 연결",
  "OBJ_FIND_FIRSTHAND_TESTIMONY": "당사자 본인의 진술(E30) 확인",
  "OBJ_CHECK_DRAFT_EMAIL": "신기범의 일정 알림과 미발송 메일(E20) 확인",
  "OBJ_VERIFY_EMAIL_CLAIMS": "메일 속 주장을 기록으로 확인",
  "OBJ_FIND_CARD_USER": "임시 카드를 실제로 쓴 사람 좁히기",
  "OBJ_FIND_SHUTDOWN_REASON": "CCTV를 멈춘 이유 찾기",
  "OBJ_RECONSTRUCT_ROUTE": "계단 주변 동선 재구성",
  "OBJ_CHECK_REFLECTION": "반사상 속 인물의 알리바이 확인",
  "OBJ_CHECK_POST_EVENT": "사건 뒤 기록 변화 확인",
  "OBJ_TRACE_DELETE": "삭제 요청의 흔적 추적",
  "OBJ_VERIFY_MOTIVE": "동기 확인",
  "OBJ_CHALLENGE_ALIBI": "알리바이 반박",
  "OBJ_FINAL_RECONSTRUCTION": "최종 재구성",
  "OBJ_COMPLETE_OLD_CASE": "10년 전 사건까지 정리"
}

export function objectiveLabel(id: string): string {
  return Object.prototype.hasOwnProperty.call(labels, id)
    ? labels[id]
    : '서버에서 제공한 수사 목표 (안내 문구 확인 필요)'
}

export function objectiveStatusLabel(status: string): string {
  switch (status.toUpperCase()) {
    case 'ACTIVE':
    case 'IN_PROGRESS':
    case 'AVAILABLE':
    case 'UNLOCKED':
      return '진행 중'
    case 'COMPLETE':
    case 'COMPLETED':
    case 'DONE':
      return '완료'
    default:
      return status
  }
}
