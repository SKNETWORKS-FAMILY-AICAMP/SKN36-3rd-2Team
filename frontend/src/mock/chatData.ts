// mock 서버 전용 시연 데이터. 공개된 최초 진술과 말투만 사용한다.
// 실제 해금 규칙/증거 조합과 무관한 "시연용" 규칙이다 (실제 판정은 백엔드).

export type Category = 'schedule' | 'victim' | 'past' | 'default'

export function classify(text: string): Category {
  if (/시간|언제|어디|저녁|17일|그날|알리바이|행적|뭐\s?했|있었/.test(text)) return 'schedule'
  if (/신기범|기범|피해자|사망|죽|사건|발견/.test(text)) return 'victim'
  if (/서윤|2016|10년|졸업|실종|편지|과거/.test(text)) return 'past'
  return 'default'
}

type Lines = Record<Category | 'present', string>

export const NPC_LINES: Record<string, Lines> = {
  C01: {
    schedule: '저녁에 신기범 씨와 운영 문제를 의논했습니다. 다툰 적 없습니다. 20시 28분에 나왔습니다.',
    victim: '안타까운 일입니다. 다만 그건 확인된 사실이 아닙니다. 추측으로 말씀드릴 수는 없습니다.',
    past: '10년 전 일이라면 학교 기록에 남은 것이 전부입니다. 그건 확인된 사실이 아닙니다.',
    default: '질문의 요지를 조금 더 분명히 해 주시겠습니까. 아는 범위에서 답하겠습니다.',
    present: '그 자료는 보았습니다. 다만 그것만으로 단정할 수는 없지 않겠습니까.',
  },
  C02: {
    schedule: '20시 30분부터 숙소에서 장부를 정리했어요. 그날 기범 씨를 만나지 않았습니다.',
    victim: '유감입니다. 자세한 건 원장과 승인 기록을 보시면 됩니다.',
    past: '오래된 일이에요. 지금 이 자리와는 별개로 봐야 합니다.',
    default: '질문을 구체적으로 해 주세요. 날짜와 절차가 있다면 그쪽이 정확합니다.',
    present: '그 날짜의 승인 절차부터 확인하셔야 합니다. 저는 그 이상 말씀드릴 게 없어요.',
  },
  C03: {
    schedule: '창고에서 시설을 점검했습니다. 공용 카드는 전부 반납됐을 겁니다.',
    victim: '저도 놀랐습니다. 규정상 건물 점검 외에는 제가 아는 게 없습니다.',
    past: '그때는 저도 학생이었잖아요. 그게… 규정상 그렇습니다.',
    default: '그건 제 담당이 아니라서요. 규정상 그렇습니다.',
    present: '아, 그건… 그러니까 절차대로 처리한 건데요. 규정상 그렇습니다.',
  },
  C04: {
    schedule: 'CCTV는 정기 점검으로 잠시 꺼둔 겁니다.',
    victim: '보안 총괄로서 책임을 느낍니다. 그 이상은 공개할 수 없습니다.',
    past: '관계없는 질문입니다.',
    default: '그건 공개할 수 없습니다.',
    present: '확인했습니다. 제 실수라면 인정합니다. 그 이상은 아닙니다.',
  },
  C05: {
    schedule: '21시 52분 후지이 류의 연락을 받고 달려갔습니다. 현장 상태만 확인했습니다.',
    victim: '제가 본 것과 추측은 구분해서 말씀드리겠습니다. 위험한 단정은 피하고 싶습니다.',
    past: '그 일은 저도 오래 마음에 남아 있습니다. 다만 지금은 확인된 것만 말씀드릴게요.',
    default: '관찰한 것과 제 추측을 나눠서 답하겠습니다. 어떤 부분이 궁금하세요?',
    present: '제가 직접 본 범위에서만 말씀드릴 수 있어요. 그 자료는 판단을 보태기 어렵습니다.',
  },
  C06: {
    schedule: '저는 행사 자료만 정리했어요. 자세한 시간은… 잠시만요, 기억을 더듬어 보겠습니다.',
    victim: '…(잠시 멈춤) 믿기 어려운 일입니다. 조심스럽게 말씀드리겠습니다.',
    past: '서윤이와 친했지만 특별한 편지를 받았다는 기억은 없습니다.',
    default: '정확히 말씀드리고 싶어서요. 질문을 한 번만 더 들려주시겠어요?',
    present: '그건… 제가 말씀드릴 수 있는 부분이 많지 않습니다.',
  },
  C07: {
    schedule: '17일 오후에 업무 보고 19시 10분 돌아갔습니다. 문지혜 씨는 따로 만나지 않았습니다.',
    victim: '하, 참… 이런 자리에서 농담할 순 없죠. 정말 안타깝습니다.',
    past: '옛날얘기요? 그땐 다들 철없었죠. 제가 뭘 안다고요.',
    default: '그건 제가 말씀드리기보단 다른 분께 여쭤보시는 게 빠를 겁니다. 하하, 아닙니다.',
    present: '…그건 제 소관이 아니었어요. 그쪽 담당자에게 확인해 보세요.',
  },
  C08: {
    schedule: '저는 학교를 오래전에 떠났고 17일에는 가지 않았습니다.',
    victim: '안타깝다고 해야 할 자리겠죠. 그 이상의 감상은 사양하겠습니다.',
    past: '…그 시절 이야기는 하고 싶지 않군요. 필요한 사실만 묻고 가시죠.',
    default: '용건만 말씀하시죠. 불필요한 감정은 서로 생략하는 게 낫지 않겠습니까.',
    present: '그런 자료가 저와 무슨 상관인지 모르겠군요.',
  },
  C09: {
    schedule: '저녁 내내 숙소에 있었습니다. 21시 50분쯤 물을 마시러 본관에 갔다가 발견했습니다.',
    victim: '그 광경은… 말로 옮기기 어렵습니다. 카메라를 든 사람이라도요.',
    past: '그해의 영상은 제가 잘 기억하고 있습니다. 하지만 지금은… 설명이 어렵습니다.',
    default: '그것은 영상을 봐야 설명할 수 있습니다. 지금은 조금 어렵습니다.',
    present: '이것은… 촬영 쪽 이야기라서, 지금은 설명하기 어렵습니다.',
  },
  C10: {
    schedule: '지금은 데이터 감사 사업을 합니다. 신기범과 따로 연락한 일은 없습니다.',
    victim: '충격이죠. 근데 왜 저한테 그걸 묻죠? 증인으로 나서고 싶진 않습니다.',
    past: '10년 전 얘기는 왜요? 질문이 뭔지 정확히 알려주세요. 증인으로 나서고 싶진 않습니다.',
    default: '그걸 왜 물으시는데요? 질문 의도부터 알려주세요.',
    present: '그거, 제가 말해야 하는 건가요? 증인으로 나서고 싶진 않다고 했잖아요.',
  },
}

/** 시연용 규칙: (인물, 질문 유형) 첫 발화 시 이벤트 발생. 실제 해금 그래프와 무관. */
export interface DemoRule {
  npc: string
  cat: Category
  evidence?: string
  unlock?: string[]
}

export const DEMO_RULES: DemoRule[] = [
  { npc: 'C01', cat: 'schedule', evidence: 'E01', unlock: ['C05'] },
  { npc: 'C05', cat: 'schedule', evidence: 'E10', unlock: ['C09'] },
  { npc: 'C09', cat: 'schedule', unlock: ['C03', 'C04'] },
]

export interface DemoEvidence {
  id: string
  title: string
  body: string
  holderId: string
  score: number
  relations: { id: string; label: string }[]
  documents?: { id: string; label: string; title: string; body: string }[]
}

// 시연용 자리표시 증거: 내용은 짧은 가짜 문구이며 실제 사건 증거가 아니다.
export const DEMO_EVIDENCE: Record<string, DemoEvidence> = {
  E01: {
    id: 'E01',
    title: '행사 방명록 사본 (시연용)',
    body: '행사 당일 서명한 이름과 시각이 적힌 사본. 실제 증거 내용은 서버에서 내려옵니다.',
    holderId: 'C01',
    score: 2,
    relations: [{ id: 'C01', label: '서명 확인' }],
  },
  E10: {
    id: 'E10',
    title: '현장 최초 확인 메모 (시연용)',
    body: '현장에 처음 도착한 사람이 남긴 짧은 메모. 실제 증거 내용은 서버에서 내려옵니다.',
    holderId: 'C05',
    score: 1,
    relations: [{ id: 'C05', label: '작성자' }],
  },
}

/** 개발용: 10칸 배치 확인용 가짜 증거 (제목 길이를 일부러 다르게). 규칙/점수에는 쓰이지 않는다. */
export const DEMO_FILLER: Record<string, DemoEvidence> = Object.fromEntries(
  ['E02','E03','E04','E05','E06','E07','E08','E09'].map((id, i) => [id, {
    id,
    title: ['짧은 제목', '조금 긴 제목의 시연용 증거 자료', '아주 길게 이어지는 제목의 시연용 증거 자료 사본(원본 대조용)', '제목', '봉투 외관 기록(시연용)', '시연용 열람 기록', '매우 매우 길게 이어지는 제목의 시연용 증거 자료 보관 기록 사본 문서', '메모'][i],
    body: '10칸 배치 확인용 가짜 증거입니다.',
    documents: id === 'E05' ? [
      { id: 'E05-a', label: '가림본', title: '기록 사본 (일부 가림, 시연용)', body: '일부 글자가 가려진 사본입니다. 시연용 문구입니다.' },
      { id: 'E05-b', label: '원본 대조', title: '기록 원본 (시연용)', body: '가림 없이 전체가 보이는 원본입니다. 시연용 문구입니다.' },
    ] : undefined,
    holderId: ['C01','C02','C03','C04','C05','C06','C07','C08'][i],
    score: 1,
    relations: [],
  }]),
)

/** 시연용 관계선. 증거를 확보하면 서버가 허용한 것처럼 내려준다. 실제 관계와 무관. */
export const DEMO_EDGES = [
  { id: 'D1', source: 'C01', target: 'C05', label: '행사 관련 (시연용)', needs: 'E01' },
  { id: 'D2', source: 'C05', target: 'C09', label: '현장 관련 (시연용)', needs: 'E10' },
]
