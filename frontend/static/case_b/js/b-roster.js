// =============================================================
// b-roster.js — 인물의 공개 정보(이름·직함·초상 파일)
// 처음부터 공개되는 정보만 둡니다. 비밀·해금 조건은 절대 넣지 않습니다.
// 누가 보이는지는 서버의 unlockedCharacters가 정합니다.
// =============================================================
window.B = window.B || {};

B.roster = {
  C01: { name: '윤태식',   role: '재단 이사장' },
  C02: { name: '문지혜',   role: '재단 자산운용 책임자' },
  C03: { name: '박도현',   role: '시설운영사 후계자' },
  C04: { name: '최민석',   role: '보안 총괄' },
  C05: { name: '정유라',   role: '의사' },
  C06: { name: '주청',     role: '투자회사 전략 담당' },
  C07: { name: '장현우',   role: '물류기업 후계자' },
  C08: { name: '서미란',   role: '전 교직원' },
  C09: { name: '후지이 류', role: '미디어 제작자' },
  C10: { name: '오재민',   role: '데이터 감사' }
};

// 인물 ID로 이름을 찾습니다. 모르는 ID면 ID를 그대로 돌려줍니다.
B.personName = function (id) {
  return (B.roster[id] && B.roster[id].name) || id;
};

// 인물 ID로 초상 이미지 경로를 만듭니다. (예: static/case_b/img/characters/C01_calm.webp)
B.personImage = function (id) {
  return B.config.IMG_BASE + 'characters/' + id + '_calm.webp';
};
