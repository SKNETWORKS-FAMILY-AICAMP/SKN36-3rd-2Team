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
│  │  └─ store.js             공통 상태 골격 (A 작성 예정)
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
| `CASE.api.getBase()` / `setBase(url)` | static/common/api.js | 서버 주소 읽기·바꾸기(주소 미확정) | B |
| (작성 예정) | static/common/store.js | 공통 상태 조회·갱신·구독 | A |

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

(A가 채움)
