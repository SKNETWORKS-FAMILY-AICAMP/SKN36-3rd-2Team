// =============================================================
// b-config.js — B 담당 화면의 설정값을 한곳에 모은 파일
// 다른 파일은 모두 이 값을 읽어서 씁니다. 바꿀 일이 생기면 여기만 고치세요.
// =============================================================
window.B = window.B || {};

B.config = {
  // 서버 주소는 공통 파일 common/api.js에서 정합니다(CASE.api.setBase).

  // true  = 모의 응답(dev/b-mock.js를 불러온 페이지에서만 동작)
  // false = 실제 FastAPI 서버에 요청 (11/30 백엔드 통합 때 false로)
  USE_MOCK: true,

  // 공개 이미지 폴더. 기본값은 데모(static/case_b/dev/demo.html) 기준 상대 경로로
  // 기존 이미지 frontend/public/assets/ 를 가리킵니다. Django 화면은 scripts.html에서 덮어씀.
  IMG_BASE: '../../../public/assets/',

  TIMEOUT_MS: 15000,        // 일반 요청 대기 시간
  CHAT_TIMEOUT_MS: 90000,   // 대화 요청 대기 시간(AI 답변이 느림)
  QUESTION_MAX: 200,        // 서버가 받는 질문 최대 글자 수

  // 증거만 제시하고 질문을 비웠을 때 보낼 문장(기존 React와 같은 문장)
  PRESENT_DEFAULT_QUESTION: '이 증거에 대해 설명해 주세요.',

  // 타임라인 탭: 서버 API가 없어 팀 결정 전까지 숨깁니다.
  SHOW_TIMELINE: false,

  // E30 동의 모달을 띄우는 서버 신호의 필드 이름.
  // 아직 백엔드에 없습니다. 이름이 정해지면 여기만 바꿉니다.
  CONSENT_FLAG: 'consentRequest',

  // 엔딩 화면 "처음으로" 버튼이 갈 주소. Django에서는 {% url %}로 덮어씀(공유안: / 기준)
  HOME_URL: './',

  // 브라우저 저장소(localStorage) 키 앞부분
  STORAGE_PREFIX: 'case001-b:'
};
