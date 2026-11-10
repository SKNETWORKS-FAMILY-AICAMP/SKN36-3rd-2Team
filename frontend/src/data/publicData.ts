// 번들에 넣어도 되는 공개 데이터만 둔다.
// 범인, 정답 조합, 증거별 점수, 해금 조건, 미해금 증거 본문은 넣지 않는다.

export const GAME_TITLE = {
  prefix: '마지막 기록',
  main: '졸업하지 못한 밤',
  case: 'CASE 001 · 세린국제학교 구 본관',
}

export const ALBUM_TEXT = {
  titleKo: '세린국제학교 — 졸업앨범 (2016년)',
  titleEn: 'Serin International School — Class of 2016',
  quote: '10년 전, 우리는 모두 같은 교실에 있었다.',
}

export const PHOTO_CAPTION = '세린국제학교 2016 졸업반 기념사진'

// 인트로 자막 (대본 S00)
export const TIMELINE_LINES = [
  '2016.10.12 · 졸업반 기념사진',
  '2016.10.17 · 백서윤 실종 · 자발적 가출 추정',
  '2026.10.17 · 세린국제학교 구 본관',
]

// 사건 시작 안내 (WORLD-CASE-INTRO)
export const CASE_INTRO = {
  heading: '형사 수사 개시',
  lines: [
    '2026년 10월 17일 밤, 신기범이 세린국제학교 구 본관의 내부 계단 아래에서 발견되었다.',
    '이곳은 2016년 졸업생과 당시 교직원을 위해 예약된 비공개 10주년 동창회 공간이다.',
    '현재 사건 관계자는 신기범을 포함해 11명, 최초 조사 가능한 인물은 윤태식이다.',
  ],
  notes: [
    { id: 'N1', text: '기록실 문은 안쪽에서 잠겨 있지 않았다.' },
    { id: 'N2', text: '신기범 사무실 서랍에 누군가 열람한 흔적이 있다.' },
  ],
  closing: '추락인지 타살인지는 초기 관찰만으로 확정되지 않았다.',
}

/** 증거 칸 수와 번호만 공개한다. 내용은 획득 후 서버가 내려준다. */
export const EVIDENCE_SLOTS = ['E01', 'E02', 'E03', 'E04', 'E05', 'E06', 'E07', 'E08', 'E09', 'E10']
