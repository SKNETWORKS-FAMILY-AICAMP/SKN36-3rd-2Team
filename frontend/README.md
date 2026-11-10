# 프론트엔드 — 마지막 기록: 사라진 공동체

React 18 + TypeScript + Vite 기반 AI 추리 게임 인터페이스입니다.

NPC와 자유롭게 대화하고, 증거를 수집하며, 인물 관계를 탐색하고, 범인을 지목하는 화면을 제공합니다.

실제 FastAPI 서버와 연결하는 HTTP 모드와 백엔드 없이 실행하는 Mock 모드를 지원합니다.

---

## 1. 기술 스택

| 기술 | 용도 |
|---|---|
| React 18 | 화면 구성 |
| TypeScript | 타입 검증 |
| Vite | 개발 서버 및 빌드 |
| React Router | 화면 라우팅 |
| Zustand | 상태 관리 |
| Framer Motion | 화면 전환 애니메이션 |
| Lucide React | UI 아이콘 |
| CSS Modules | 화면 및 컴포넌트 스타일 |

---

## 2. 설치 및 실행

### 설치

```powershell
cd frontend

npm ci
```

### 개발 서버

```powershell
npm run dev
```

접속 주소:

http://localhost:5173

### 빌드

```powershell
npm run build
```

### 빌드 결과 확인

```powershell
npm run preview
```

### 정답 유출 검사

```powershell
npm run spoiler
```

배포용 빌드 생성 후 검사하는 것을 권장합니다.

---

## 3. API 연결 모드

프론트엔드는 두 가지 실행 모드를 제공합니다.

| 모드 | 설명 |
|---|---|
| `mock` | 실제 백엔드 없이 개발 및 시연 |
| `http` | 실제 FastAPI 서버 연결 |

### 기본 모드 설정

`frontend/.env` 파일을 생성해 기본 실행 모드를 설정할 수 있습니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=/api
VITE_CHAT_TIMEOUT_MS=90000
```

`VITE_API_BASE_URL=/api`는 Vite 개발 서버의 프록시 설정을 이용합니다.

`vite.config.ts`에서 `/api` 요청은 `http://127.0.0.1:8000`으로 전달됩니다.

### 주소로 모드 전환

실제 API 모드:

```text
http://localhost:5173/?api=http#/
```

Mock 모드:

```text
http://localhost:5173/?api=mock#/
```

저장된 모드 초기화:

```text
http://localhost:5173/?api=reset#/
```

브라우저에서 선택한 모드는 로컬 저장소에 기억됩니다.

기본 환경변수를 변경했는데 모드가 바뀌지 않는 경우 `?api=reset`으로 초기화할 수 있습니다.

Mock 모드에서는 화면에 `시연용 데이터` 표시가 나타납니다.

---

## 4. 폴더 구조

```text
frontend/
├── public/
│   └── assets/
│       ├── album/           # 인물 앨범 이미지
│       ├── group/           # 단체사진
│       └── logo/            # 로고
│
├── scripts/
│   └── spoiler-check.mjs    # 정답 및 비공개 데이터 검사
│
├── src/
│   ├── api/                 # FastAPI 및 Mock API
│   ├── components/          # 공통 UI 컴포넌트
│   ├── data/                # 인물 등 공개 정적 데이터
│   ├── mock/                # Mock 게임 데이터
│   ├── screens/             # 게임 화면
│   ├── store/               # Zustand 상태 관리
│   ├── styles/              # 공통 스타일
│   ├── App.tsx              # 화면 라우터
│   ├── config.ts            # UI 설정
│   └── main.tsx             # React 시작점
│
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

상세 파일별 역할은 [src 디렉터리 안내](./src/README.md)를 참고하세요.

---

## 5. 화면 구성

라우팅은 React Router의 `HashRouter`를 사용합니다.

| 화면 | 경로 | 주요 파일 | 역할 |
|---|---|---|---|
| 메인 | `/#/` | `screens/Main/Main.tsx` | 게임 시작 |
| 스토리 | `/#/story` | `screens/Story/Story.tsx` | 사건 도입 |
| NPC 대화 | `/#/chat/:npcId` | `screens/Chat/Chat.tsx` | NPC 대화 |
| 증거 | `/#/evidence` | `screens/Evidence/Evidence.tsx` | 증거 확인 |
| 관계도 | `/#/relations` | `screens/Relations/Relations.tsx` | 인물 관계 |
| 수첩 | `/#/notes` | `screens/Notes/Notes.tsx` | 조사 기록 |
| 지목 | `/#/accuse` | `screens/Accuse/Accuse.tsx` | 범인 지목 |
| 엔딩 | `/#/final` | `screens/Final/Final.tsx` | 결과 확인 |

화면 전환은 Framer Motion을 이용합니다.

---

## 6. API 모듈

경로: `src/api/`

| 파일 | 역할 |
|---|---|
| `client.ts` | GameApi 인터페이스 및 모드 선택 |
| `httpApi.ts` | 실제 FastAPI 요청 |
| `mockApi.ts` | Mock 데이터 기반 API |
| `types.ts` | 게임 데이터 및 API 타입 |

### 연결 구조

```text
React Screens
     ↓
GameApi
     ↓
client.ts
     ├── mockApi.ts
     └── httpApi.ts
             ↓
          FastAPI
```

컴포넌트는 직접 API 요청을 만들기보다 공통 GameApi 인터페이스를 사용합니다.

### 주요 기능

- 게임 생성 및 상태 조회
- NPC 대화
- 이전 대화 기록 조회
- 증거 제시 및 수집
- 증거 상세 정보 조회
- 인물 관계도 조회
- 범인 지목 및 엔딩 조회

실제 게임 판정은 백엔드 GameState를 기준으로 수행합니다.

---

## 7. 상태 관리

경로: `src/store/`

| 파일 | 역할 |
|---|---|
| `gameStore.ts` | 게임 진행 상태 및 화면 연동 |
| `chatStore.ts` | NPC 대화 상태 |
| `noteStore.ts` | 조사 메모 관련 상태 |

Zustand는 프론트엔드의 화면 상태 관리에 사용합니다.

서버가 관리하는 증거 점수, NPC 해금, 남은 지목 횟수 및 범인 판정은 클라이언트에서 임의로 변경하지 않습니다.

---

## 8. 주요 UI 컴포넌트

경로: `src/components/`

| 파일 | 역할 |
|---|---|
| `CharacterPortrait.tsx` | NPC 이미지 표시 |
| `Notebook.tsx` | 수첩 UI |
| `NotesPanel.tsx` | 메모 패널 |
| `PlaceScene.tsx` | 장소 장면 연출 |
| `PosterScene.tsx` | 포스터 연출 |
| `RainCanvas.tsx` | 비 효과 |
| `Toasts.tsx` | 게임 이벤트 알림 |
| `TopNav.tsx` | 상단 내비게이션 |

각 컴포넌트는 해당 CSS Module과 함께 관리합니다.

---

## 9. 이미지 및 정적 리소스

주요 경로: `public/assets/`

### 현재 등록된 이미지

| 경로 | 내용 |
|---|---|
| `album/C01.webp` ~ `C10.webp` | NPC 앨범 이미지 |
| `album/M01.webp` | 추가 앨범 이미지 |
| `album/V01.webp` | 추가 앨범 이미지 |
| `group/group2016.webp` | 단체사진 |
| `logo/logo.svg` | 로고 |

인물 표시 이름과 이미지 경로는 `src/data/characters.ts`에서 관리합니다.

일부 화면에서 별도의 인물 이미지가 없으면 등록된 앨범 이미지를 대체 리소스로 사용합니다.

### 이미지 교체

기존 파일 이름과 경로를 유지하면 코드 수정 없이 이미지 리소스를 교체할 수 있습니다.

이미지 교체 후 다음 명령을 실행해 빌드 오류를 확인합니다.

```powershell
npm run build
```

---

## 10. 백엔드 연동 규칙

### 게임 상태

프론트엔드는 백엔드 응답을 기준으로 다음 데이터를 갱신합니다.

| 응답 필드 | 용도 |
|---|---|
| `sessionId` | 현재 세션 |
| `phase` | 게임 단계 |
| `activeCharacterId` | 현재 NPC |
| `unlockedCharacters` | NPC 해금 |
| `collection.score` | 증거 점수 |
| `collection.total` | 증거 총점 |
| `canAccuse` | 범인 지목 가능 여부 |
| `attemptsLeft` | 남은 지목 기회 |
| `outcome` | 게임 결과 |
| `revision` | 상태 변경 버전 |
| `events` | 알림 및 화면 갱신 |

### NPC 대화

API:

```text
POST /api/games/{session_id}/chat
```

일반 대화 요청:

```json
{
  "question": "어제 어디에 계셨나요?",
  "presentedEvidenceId": null
}
```

증거 제시 요청:

```json
{
  "question": "이 증거에 대해 설명해 주세요.",
  "presentedEvidenceId": "E01"
}
```

화면에는 서버에서 검증한 `display_text`를 표시합니다.

### 증거 수집

프론트엔드는 서버가 수집 가능하다고 응답한 증거를 표시합니다.

획득 요청은 별도의 수집 API를 통해 수행합니다.

### 범인 지목

프론트엔드는 `canAccuse`를 기준으로 지목 버튼의 사용 가능 여부를 표시합니다.

실제 판정은 FastAPI가 수행합니다.

`NOT_ENOUGH_EVIDENCE` 응답에서는 지목 기회가 감소하지 않습니다.

---

## 11. 오류 및 중복 요청 처리

### HTTP 오류

백엔드 오류 응답의 `message` 또는 `detail`을 우선 사용합니다.

### 대화 타임아웃

기본 NPC 대화 요청 제한 시간은 90초입니다.

환경변수 `VITE_CHAT_TIMEOUT_MS`를 사용해 변경할 수 있습니다.

### 중복 요청

- 동일 세션의 동시 대화 요청을 제한합니다.
- 지원되는 브라우저에서는 Web Locks를 활용합니다.
- 서버에서도 revision 및 트랜잭션으로 상태를 검증합니다.
- 응답이 지연되었다고 해서 상태 확인 없이 같은 요청을 자동 재전송하지 않습니다.

---

## 12. Mock 모드 및 개발 도구

Mock 모드는 실제 Ollama 및 데이터베이스가 없어도 주요 UI 흐름을 확인할 수 있도록 제공합니다.

주요 사용 목적:

- 화면 개발
- 프론트엔드 단독 점검
- 발표 시연
- API 장애 상황의 대체 시연

Mock 데이터는 다음 경로에서 관리합니다.

- `src/mock/chatData.ts`
- `src/mock/publicData.ts`
- `src/api/mockApi.ts`

Mock 모드에서 제공하는 개발용 기능과 실제 서버 데이터는 구분해야 합니다.

`src/config.ts`에는 일부 이전 개발 단계에서 사용한 UI 설정값이 남아 있으므로, 서버 판정 규칙의 기준으로 사용하지 않습니다.

---

## 13. 보안 및 주의사항

- 실제 사건 정답을 프론트엔드에 하드코딩하지 않습니다.
- 비공개 시나리오 파일을 `public/`에 추가하지 않습니다.
- API Key를 `VITE_` 환경변수에 저장하지 않습니다.
- NPC 메시지는 일반 문자열로 안전하게 렌더링합니다.
- 서버가 공개한 증거와 관계 정보만 표시합니다.
- 세션 소유권 검증을 우회하지 않습니다.
- 배포 전에 `npm run spoiler`를 실행합니다.

---

## 14. 관련 문서

- [프로젝트 전체 README](../README.md)
- [프론트엔드 src 구조](./src/README.md)
- [API 모듈](./src/api/README.md)
- [화면 모듈](./src/screens/README.md)
- [상태 관리](./src/store/README.md)
- [시스템 아키텍처](../docs/architecture/01-system-overview.md)
- [모듈 인터페이스](../docs/architecture/03-module-interfaces.md)