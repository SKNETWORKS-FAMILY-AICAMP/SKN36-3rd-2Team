
# Django 화면 공통 구조·슬롯 ID (#166)

기존 React(`src/`, `public/`)는 보존하고, Django 화면은 `templates/`와 `static/`에서 개발합니다.
Django 설정(템플릿·정적 폴더 등록)과 URL 연결은 백엔드 담당자와 협의 후 진행합니다.

## 폴더

```
frontend/
├─ templates/                 Django 템플릿
│  ├─ base.html, main.html, play.html   (A 작성 예정)
│  └─ partials/
│     ├─ case_a/              A 조각
│     └─ case_b/              B 조각
├─ static/
│  ├─ common/
│  │  ├─ api.js               공통 요청 골격 (B)
│  │  └─ store.js             공통 상태 골격 (A)
│  ├─ case_a/                 A 전용 CSS·JS
│  └─ case_b/                 B 전용 CSS·JS (dev/는 개발용, 배포 템플릿에서 불러오지 않음)
├─ public/assets/             기존 이미지 (새 이미지도 같은 폴더 규칙)
└─ src/                       기존 React 코드 보존
```

협의 필요(백엔드): `frontend/templates`를 TEMPLATES DIRS에, `frontend/static`·`frontend/public`을 STATICFILES_DIRS에 등록, `/`·`/play/` URL과 views.

## 공통 함수

| 이름 | 파일 | 하는 일 | 작성 |
|---|---|---|---|
| `CASE.api.request(path, options, timeoutMs)` | static/common/api.js | 서버 요청(쿠키 포함, 기본 15초, 오류 문구 throw, 자동 재시도 없음) | B |
| `CASE.api.once(key, fn)` | static/common/api.js | 같은 요청 중복 방지 | B |
| `CASE.api.getBase()` / `CASE.api.setBase(url)` | static/common/api.js | 서버 주소 읽기·바꾸기(주소 미확정) | B |
| `CASE.store.getState()` | static/common/store.js | 현재 공통 상태 조회 | A |
| `CASE.store.setState(newState)` | static/common/store.js | 공통 상태 일부 갱신 | A |
| `CASE.store.setGameState(gameState)` | static/common/store.js | 서버에서 받은 게임 상태 반영 | A |
| `CASE.store.subscribe(listener)` | static/common/store.js | 상태 변경 구독 및 구독 해제 함수 반환 | A |
| `CASE.store.resetState()` | static/common/store.js | 전체 상태 초기화 | A |

## 공통 상태 (store.js)

| 상태 변수 | 초기값 | 설명 |
|---|---|---|
| `gameState` | `null` | 서버에서 전달받은 게임 상태 |
| `currentScreen` | `'investigation'` | 현재 화면 |
| `currentLocation` | `null` | 현재 조사 장소 |
| `selectedNpc` | `null` | 현재 선택한 NPC |
| `isLoading` | `false` | 요청 처리 상태 |
| `error` | `null` | 오류 정보 |

### 공통 사용 규칙

- A와 B는 `window.CASE` 공통 객체를 사용합니다.
- 서버 요청은 `CASE.api`, 공통 상태 관리는 `CASE.store`를 사용합니다.
- `api.js`, `store.js`는 A·B 담당 JavaScript 파일보다 먼저 불러옵니다.
- 상태 조회는 `getState()`, 상태 갱신은 `setState()`를 사용합니다.
- 서버에서 받은 전체 게임 상태는 `setGameState()`를 통해 반영합니다.
- 상태 변경에 따른 화면 갱신은 `subscribe()`를 사용합니다.
- 구독이 더 이상 필요하지 않으면 반환된 구독 해제 함수를 호출합니다.
- A가 획득한 증거는 서버 응답 및 공통 상태를 통해 B의 증거함에 반영합니다.
- 증거 획득, NPC·장소 해금, 범인 판정, 엔딩 조건 등은 프론트엔드에서 자체 판정하지 않습니다.
- `gameState` 내부 필드 및 세션 관리 방식은 실제 백엔드 API 명세 확인 후 연결합니다.
- 현재 상태 변수는 프론트엔드 공통 관리용이며 백엔드 API 필드명과 동일하다는 의미는 아닙니다.

### 공통 상태 사용 예시

```javascript
// 현재 상태 조회
const state = CASE.store.getState();

// 화면 상태 변경
CASE.store.setState({
    currentScreen: 'interview'
});

// 서버에서 받은 전체 게임 상태 반영
CASE.store.setGameState(gameState);

// 상태 변경 구독
const unsubscribe = CASE.store.subscribe(function (state) {
    console.log(state);
});

// 필요 시 구독 해제
unsubscribe();

// 전체 상태 초기화
CASE.store.resetState();
```

## B 슬롯 (templates/partials/case_b/)

| 조각 | 넣는 곳(play.html) | ID |
|---|---|---|
| slot_people.html | 왼쪽 칸 | `b-people` |
| slot_interview.html | 가운데, 면담실일 때 | `b-interview` |
| tools.html | 도구 칸 | `b-evidence-btn`, `b-evidence-count`, `b-relations-btn`, `b-records-btn`, `b-accuse-btn` |
| scripts.html | 맨 아래 | B CSS·JS 불러오기 |

튜토리얼 B 단계 대상: `b-people`, `b-question`, `b-evidence-btn`, `[data-b-present]`, `b-send`
챕터 표시: `b-chapter`

## A 슬롯

(A가 담당 화면 개발 시 작성)
