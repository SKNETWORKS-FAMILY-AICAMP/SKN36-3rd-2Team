import type { EndingKey } from './endings'

export interface SceneLine {
  /** 인물 ID(C01~), 'narration'(해설), 또는 표시할 이름(예: '수사관') */
  speaker: string
  text: string
  /** 배경 이미지(public/assets 기준 경로). 있으면 인물 사진 대신 장면 이미지를 보여준다 */
  image?: string
  /** true 면 대사 상자 없이 이미지를 통째로 보여주는 결과 카드(이미지 안에 글자가 있음). text 는 스크린리더용 설명 */
  card?: boolean
  /** 제시한 증거 사진(전체 경로). 있으면 인물 사진 대신 증거 사진을 보여준다 */
  evidenceSrc?: string
}

const IMG = {
  unproven: 'assets/ending/unproven.webp',
  escaped: 'assets/ending/escaped.webp',
  cardUnproven: 'assets/ending/card_unproven.webp',
  cardEscaped: 'assets/ending/card_escaped.webp',
  group2016: 'assets/group/group2016.webp',
}

/** 엔딩별 기본 대사. 서버가 ending.scene 을 주면 그것이 우선한다.
 *  범인을 밝히지 않는 엔딩(증거 부족·실패)에는 범인 이름·정체를 쓰지 않는다. */
export function defaultScene(key: EndingKey, suspectId: string): SceneLine[] {
  switch (key) {
    case 'NO_EVIDENCE':
      return [
        { speaker: 'narration', text: '증거가 부족하다. 지금 가진 기록만으로는 누구도 붙잡을 수 없다.', image: IMG.unproven },
        { speaker: 'narration', text: '그 밤 계단에서 무슨 일이 있었는지 아는 사람은, 아무 일도 없었다는 듯 복도를 지나간다.', image: IMG.unproven },
        { speaker: '???', text: '……역시, 그냥 넘어갔네.', image: IMG.unproven },
        { speaker: 'narration', text: '사건은 닫히지 않은 채 남았다.', image: IMG.unproven },
        { speaker: 'narration', text: '증거 부족 — 단서가 충분하지 않아 진실에 닿지 못했다.', image: IMG.cardUnproven, card: true },
      ]
    case 'UNSOLVED':
      return [
        { speaker: 'narration', text: '지목은 빗나갔고, 수사는 여기서 멈췄다.', image: IMG.escaped },
        { speaker: 'narration', text: '불 꺼진 복도 끝, 그날 밤의 주인은 한 번도 뒤돌아보지 않고 어둠 속으로 사라진다.', image: IMG.escaped },
        { speaker: '???', text: '……아무 일도 없었던 거야. 처음부터, 아무 일도.', image: IMG.escaped },
        { speaker: 'narration', text: '진실은 어둠 속에 남았다.', image: IMG.escaped },
        { speaker: 'narration', text: '수사 실패 — 범인을 놓쳤다. 사건은 미제로 남았다.', image: IMG.cardEscaped, card: true },
      ]
    case 'ESTIMATED':
      return [
        { speaker: 'narration', text: '지목한 사람은 시선을 피하지 않는다. 정황은 일치하지만, 입증할 증거가 모자란다.' },
        { speaker: suspectId, text: '……그건, 끝내 못 찾으셨군요.' },
        { speaker: 'narration', text: '의미심장한 미소를 남기고 그는 조사실을 나선다. 정황은 일치하나 수사상 입증이 더 필요하다.' },
        { speaker: 'narration', text: '추정 성립', image: cardPath(key), card: true },
      ]
    case 'FULL':
    case 'DEEP':
      return [
        { speaker: '수사관', text: key === 'DEEP' ? '마지막 기록까지 확인했습니다.' : '조사를 마칩니다. 사건 기록을 닫겠습니다.' },
        { speaker: 'narration', text: key === 'DEEP' ? '심화 엔딩' : '사건 해결', image: cardPath(key), card: true },
      ]
  }
}

export function cardPath(key: EndingKey) {
  const names = { FULL: 'full', DEEP: 'deep', ESTIMATED: 'estimated', NO_EVIDENCE: 'unproven', UNSOLVED: 'escaped' }
  return 'assets/ending/card_' + names[key] + '.webp'
}
