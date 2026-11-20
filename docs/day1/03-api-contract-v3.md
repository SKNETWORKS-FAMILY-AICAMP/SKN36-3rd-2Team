# Day 1 — API 계약 v3.0 설계

## 1. 문서 정보

- 프로젝트: 마지막 기록: 졸업하지 못한 밤
- 날짜: 2026-11-20
- GitHub Issue: #95
- 브랜치: feature/95-api-contract-v3
- 기준 커밋: 90e0e25
- 상태: 설계 문서 / 구현 전

## 2. 설계 원칙

1. 기존 `/api/games/...` 경로를 유지한다.
2. 기존 필드는 삭제하거나 의미를 변경하지 않는다.
3. 신규 필드는 가능한 한 선택적 필드로 추가한다.
4. 플레이어 게임 상태는 FastAPI가 단독으로 관리한다.
5. Django는 콘텐츠 관리와 게시를 담당한다.
6. Multi-Agent와 MCP는 최종 게임 판정을 수행하지 않는다.
7. 미해금 증거와 비공개 사건 정답은 공개하지 않는다.

API v3.0은 본 프로젝트의 목표 계약 버전을 의미한다.
현재 서비스에 v3.0이 구현되었다는 뜻은 아니다.

## 3. 기존 FastAPI 엔드포인트

아래 15개 엔드포인트는 기존 코드에서 확인한 실제 API이다.

| Method | Path | 기능 |
|---|---|---|
| POST | /api/games | 새 게임 생성 |
| GET | /api/games/{session_id} | 게임 상태 조회 |
| POST | /api/games/{session_id}/prologue/complete | 프롤로그 완료 |
| POST | /api/games/{session_id}/characters/{character_id}/select | NPC 선택 |
| GET | /api/games/{session_id}/chats/{character_id} | 대화 기록 |
| POST | /api/games/{session_id}/chat | NPC 대화 |
| POST | /api/games/{session_id}/evidence/{evidence_id}/collect | 증거 수집 |
| GET | /api/games/{session_id}/evidence | 수집 증거 목록 |
| GET | /api/games/{session_id}/evidence/available | 수집 가능한 증거 |
| GET | /api/games/{session_id}/evidence/{evidence_id} | 증거 상세 |
| GET | /api/games/{session_id}/evidence/{evidence_id}/photo | 증거 이미지 |
| GET | /api/games/{session_id}/progress | 진행률 |
| GET | /api/games/{session_id}/relationships | 인물 관계 |
| POST | /api/games/{session_id}/accusations | 범인 지목 |
| GET | /api/games/{session_id}/ending | 엔딩 조회 |

기존 엔드포인트와 HTTP Method를 변경하지 않는다.

## 4. 기존 GameResponse

실제 FastAPI `GameResponse` 기준 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| sessionId | string | 게임 세션 |
| phase | string | 현재 게임 단계 |
| activeCharacterId | string | 선택된 NPC |
| unlockedCharacters | string[] | 해금된 NPC |
| collection | object | 수집 점수 |
| canAccuse | boolean | 지목 가능 여부 |
| attemptsLeft | integer | 남은 지목 횟수 |
| outcome | string/null | 게임 결과 |
| revision | integer | 게임 상태 버전 |
| events | object[] | 기존 이벤트 |

기존 `collection` 구조:

```json
{
  "score": 8,
  "total": 21
}
```

위 점수는 기존 CASE-001 기준이며,
증거 확장 이후 총점은 콘텐츠 규칙에서 계산해야 한다.

## 5. GameResponse v3.0 확장

기존 필드는 유지하고 다음 필드를 추가한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| chapter | ChapterState/null | 현재 챕터 |
| objective | ObjectiveState/null | 현재 수사 목표 |
| endingKey | string/null | 확정된 엔딩 식별자 |
| accuseBlockedReason | string/null | 지목 불가 사유 |
| contentVersion | string/null | 사용 중인 콘텐츠 버전 |
| storyEvents | StoryEventPayload[] | 신규 스토리 이벤트 |

기존 클라이언트 호환을 위해 새 필드는
v3 전환 단계에서 선택적으로 추가한다.

### 5.1 ChapterState

```json
{
  "id": "CH01",
  "title": "첫 번째 기록",
  "order": 1,
  "total": 5
}
```

### 5.2 ObjectiveState

```json
{
  "id": "OBJ-CH01-01",
  "title": "첫 번째 증언 확보",
  "description": "현재 조사에서 필요한 진술을 확인합니다.",
  "status": "IN_PROGRESS"
}
```

목표 상태 값:

- LOCKED
- IN_PROGRESS
- COMPLETED

이 예시는 목표 API 스키마이며 실제 콘텐츠는 아니다.

### 5.3 GameResponse v3 예시

```json
{
  "sessionId": "example-session",
  "phase": "INVESTIGATION",
  "activeCharacterId": "C01",
  "unlockedCharacters": ["C01", "C02"],
  "collection": {
    "score": 8,
    "total": 21
  },
  "canAccuse": false,
  "attemptsLeft": 3,
  "outcome": null,
  "revision": 12,
  "events": [],
  "chapter": {
    "id": "CH01",
    "title": "첫 번째 기록",
    "order": 1,
    "total": 5
  },
  "objective": {
    "id": "OBJ-CH01-01",
    "title": "첫 번째 증언 확보",
    "description": "현재 조사에서 필요한 진술을 확인합니다.",
    "status": "IN_PROGRESS"
  },
  "endingKey": null,
  "accuseBlockedReason": "NOT_ENOUGH_EVIDENCE",
  "contentVersion": "1.0.0",
  "storyEvents": []
}
```

예시 데이터는 계약 설명용이며 실행 결과가 아니다.

## 6. 지목 불가 사유

`accuseBlockedReason`은 다음 값 중 하나로 설계한다.

| 값 | 의미 |
|---|---|
| NOT_IN_INVESTIGATION | 지목 가능한 단계가 아님 |
| NOT_ENOUGH_EVIDENCE | 필요한 증거 또는 점수 부족 |
| NO_ATTEMPTS_LEFT | 지목 기회 소진 |
| GAME_FINISHED | 게임 종료 |
| null | 지목 가능 |

실제 최종 판정은 기존 `can_accuse` 및
게임 엔진의 조건 검증 로직을 사용한다.

## 7. NPC 대화 API

기존 엔드포인트:

`POST /api/games/{session_id}/chat`

### 7.1 기존 요청

```json
{
  "question": "어젯밤에 어디에 계셨나요?",
  "presentedEvidenceId": null
}
```

증거 제시:

```json
{
  "question": "이 증거에 대해 설명해 주세요.",
  "presentedEvidenceId": "E04"
}
```

현재 구현은 `presentedEvidenceId`를
E01~E10 범위로 검증한다.

E11~E30 지원은 후속 게임 엔진 이슈에서 구현한다.

### 7.2 기존 응답

```json
{
  "characterId": "C01",
  "display_text": "검증된 NPC 응답",
  "game": {
    "sessionId": "example-session",
    "phase": "INVESTIGATION",
    "activeCharacterId": "C01",
    "unlockedCharacters": ["C01"],
    "collection": {
      "score": 0,
      "total": 21
    },
    "canAccuse": false,
    "attemptsLeft": 3,
    "outcome": null,
    "revision": 2,
    "events": []
  }
}
```

v3에서도 기존 `display_text`와 `game`을 유지한다.

신규 스토리 이벤트는 확장된
`game.storyEvents`에서 전달한다.

## 8. 스토리 이벤트 계약

기존 `events`는 문자열 기반 이벤트 목록이다.

현재 React 어댑터는 다음 이벤트를 처리한다.

- EVIDENCE_COLLECTED
- NPC_UNLOCKED

기존 구조를 유지하기 위해
복합 스토리 이벤트는 별도 `storyEvents` 필드를 사용한다.

### 8.1 StoryEventPayload

```json
{
  "eventId": "EVT-CH01-001",
  "eventKey": "CH01_FIRST_CLUE",
  "type": "STORY_EVENT",
  "chapterId": "CH01",
  "trigger": "EVIDENCE_COLLECTED",
  "payload": {
    "sceneId": "SCENE-CH01-01",
    "title": "새로운 단서",
    "message": "조사 중 새로운 사실이 확인되었습니다."
  }
}
```

필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| eventId | string | 발생 이벤트의 고유 ID |
| eventKey | string | 이벤트 콘텐츠 식별자 |
| type | string | 이벤트 분류 |
| chapterId | string | 연결 챕터 |
| trigger | string | 발생 원인 |
| payload | object | 클라이언트 표시 데이터 |

발생 이벤트는 세션과 이벤트 키를 기준으로
중복 적용되지 않도록 관리한다.

이벤트 발생 및 상태 저장은 FastAPI가 처리한다.
Django는 이벤트 콘텐츠의 정의만 관리한다.

## 9. 증거 API v3.0

기존 증거 API 경로는 유지한다.

증거 ID의 목표 지원 범위:

- 기존: E01~E10
- 목표: E01~E30

증거 목록과 점수 총합은 콘텐츠 버전별로 결정한다.

### 9.1 증거 상세 응답

기존 구조:

```json
{
  "id": "E04",
  "title": "증거 제목",
  "body": "열람이 허용된 증거 본문",
  "holderId": "C04",
  "acquiredBy": "question",
  "confirmedRelations": [],
  "documents": []
}
```

미획득 또는 미해금 증거에 대한 상세 정보는
현재 GameState와 접근 정책 검증 이후에만 반환한다.

클라이언트가 보낸 획득 여부를 신뢰하지 않는다.

## 10. 범인 지목 API

기존 엔드포인트:

`POST /api/games/{session_id}/accusations`

### 10.1 기존 요청

```json
{
  "suspectId": "C04",
  "expectedRevision": 12
}
```

`expectedRevision`은 필수 필드이다.

서버 상태 버전과 일치하지 않으면
현재 구현은 HTTP 409를 반환한다.

프론트엔드의 `evidenceIds`는
서버 지목 API 요청 본문으로 전달되지 않는다.

### 10.2 기존 응답

```json
{
  "result": "NOT_ENOUGH_EVIDENCE",
  "attemptsLeft": 3,
  "game": {
    "sessionId": "example-session",
    "phase": "INVESTIGATION",
    "activeCharacterId": "C04",
    "unlockedCharacters": ["C01", "C04"],
    "collection": {
      "score": 4,
      "total": 21
    },
    "canAccuse": false,
    "attemptsLeft": 3,
    "outcome": null,
    "revision": 12,
    "events": []
  }
}
```

### 10.3 v3 확장

- 기존 `result` 유지
- 기존 `attemptsLeft` 유지
- 기존 `game` 유지
- `game.endingKey` 추가
- `game.accuseBlockedReason` 추가

엔딩 식별자는 서버가 확정한 결과만 사용한다.
LLM이 반환한 임의의 엔딩 식별자를 신뢰하지 않는다.

## 11. Django 공개 콘텐츠 API

아래 엔드포인트는 신규 설계안이며 아직 구현되지 않았다.

| Method | Path | 목적 |
|---|---|---|
| GET | /api/content/cases | 공개 사건 목록 |
| GET | /api/content/cases/{case_id} | 사건 소개 |
| GET | /api/content/cases/{case_id}/chapters | 공개 챕터 목록 |
| GET | /api/content/cases/{case_id}/characters | 공개 NPC 프로필 |

공개 응답에 포함 가능한 정보:

- 사건 ID 및 제목
- 사건 공개 소개
- 공개된 챕터 제목
- 공개 가능한 NPC 프로필

공개 응답에서 제외할 정보:

- 진범 및 사건 정답
- 증거 획득 조건
- 미해금 증거 원문
- NPC의 비공개 지식 카드
- 관리자 전용 시나리오
- 내부 이벤트 트리거 조건

증거 상세와 해금 여부는
FastAPI 게임 API를 통해 확인한다.

## 12. Django 내부 콘텐츠 API

내부 API 경로 제안:

`GET /internal/content/releases/{version}`

서비스 인증이 통과한 경우에만
게시된 콘텐츠 스냅샷을 제공한다.

### 12.1 응답 구조

```json
{
  "caseId": "CASE-001",
  "version": "1.0.0",
  "schemaVersion": "3.0",
  "checksum": "sha256:<64-hex-characters>",
  "manifest": {
    "chapters": [],
    "characters": [],
    "evidence": [],
    "storyEvents": []
  }
}
```

`checksum` 값은 실제 구현 시 정규화된
스냅샷 직렬화 결과의 SHA-256으로 생성한다.

### 12.2 검증 정책

FastAPI는 다음을 확인한다.

1. 서비스 인증 성공 여부
2. schemaVersion 호환성
3. 콘텐츠 체크섬 일치 여부
4. 사건 ID 및 참조 무결성
5. 증거 및 NPC ID 유효성
6. 챕터·이벤트 참조 관계
7. 지원 가능한 게임 엔진 규칙

검증 실패 시 콘텐츠를 활성화하지 않는다.

## 13. 콘텐츠 버전 및 게임 세션

새 게임 생성 시 콘텐츠 버전을 고정한다.

```json
{
  "sessionId": "example-session",
  "contentVersion": "1.0.0"
}
```

실제 저장 시에는 GameState 스키마 확장과
기존 SQLite 데이터 호환성 검증이 필요하다.

기존 세션은 지정된 콘텐츠 버전을 유지한다.

기존에 저장된 버전이 없는 세션의 처리 정책은
마이그레이션 이슈에서 별도로 구현한다.

## 14. Multi-Agent 인터페이스

Multi-Agent Orchestrator는 FastAPI 내부에서 호출한다.

### 14.1 입력 계약

```json
{
  "sessionId": "example-session",
  "characterId": "C01",
  "question": "어제 어디에 계셨나요?",
  "contentVersion": "1.0.0",
  "requestId": "example-request"
}
```

이 구조는 Orchestrator 호출 계약 초안이다.

GameState와 접근 권한은 신뢰할 수 있는
서버 컨텍스트에서 별도로 주입한다.

### 14.2 출력 계약

```json
{
  "displayText": "검증된 NPC 응답",
  "usedSourceIds": [],
  "proposedEvents": [],
  "validation": {
    "passed": true,
    "reason": null
  }
}
```

Agent 출력은 상태 변경 제안일 뿐이다.

FastAPI가 접근 권한과 이벤트 조건을
최종 검증한 뒤 상태를 저장한다.

## 15. MCP Tool 계약

MCP Tool은 FastAPI가 검증한
권한 범위 내에서 읽기 전용 검색을 수행한다.

설계 대상 Tool:

| Tool | 기능 |
|---|---|
| search_evidence | 허용된 증거 검색 |
| search_character_relations | 인물 관계 검색 |
| get_authorized_context | 권한 기반 사건 문서 조회 |
| get_chapter_context | 현재 챕터 콘텐츠 조회 |

### 15.1 Tool 입력 예시

```json
{
  "query": "비상계단 목격 기록",
  "limit": 5
}
```

세션 권한, 접근 가능한 문서 범위,
현재 NPC 및 챕터 정보는
서버의 신뢰된 실행 컨텍스트에서 결정한다.

Tool 응답에는 허용된 문서만 포함한다.

Tool은 GameState, 점수, 엔딩을 직접 수정하지 않는다.

## 16. 오류 응답 계약

### 16.1 기존 FastAPI 오류

현재 구현은 FastAPI의 `detail` 필드를 사용한다.

```json
{
  "detail": "게임 상태가 변경되었습니다."
}
```

기존 응답 형식을 유지한다.

### 16.2 목표 오류 분류

| HTTP | 의미 |
|---|---|
| 400 | 잘못된 비즈니스 요청 |
| 401 | 내부 서비스 인증 실패 |
| 403 | 접근 권한 부족 |
| 404 | 세션 또는 허용된 리소스 없음 |
| 409 | 상태 버전 충돌 또는 진행 조건 불충족 |
| 422 | 요청 스키마 검증 실패 |
| 503 | 게임 판정 또는 의존 서비스 준비되지 않음 |

현재 구현에 이미 존재하는 상태 코드와
신규 서비스에서 도입할 코드를 함께 설명한 표이다.

### 16.3 향후 확장 오류 구조

```json
{
  "detail": "게임 상태가 변경되었습니다.",
  "error": {
    "code": "REVISION_CONFLICT",
    "retryable": true
  }
}
```

기존 `detail`을 제거하지 않는다.
`error` 객체는 후속 구현에서 추가할 수 있다.

## 17. React 호환성

현재 프론트엔드는 다음 파일에서 계약을 관리한다.

- frontend/src/api/types.ts
- frontend/src/api/client.ts
- frontend/src/api/httpApi.ts

프론트엔드 내부 타입과 FastAPI 응답 타입은
일부 필드명 및 구조가 다르며 어댑터에서 변환한다.

예:

- Backend `unlockedCharacters`
- Frontend `unlockedNpcs`

- Backend `display_text`
- Frontend `reply`

- Backend `EVIDENCE_COLLECTED`
- Frontend `evidence_found`

v3 적용 시 기존 어댑터를 유지하고
새 필드를 단계적으로 추가한다.

서버에서 스토리 이벤트를 전달한 뒤에는
프론트엔드에서 `storyEvents` 처리 로직을 추가해야 한다.

## 18. API 버전 관리 전략

- 기존 `/api/games/...` 경로 유지
- v3 필드를 하위 호환 방식으로 추가
- 기존 필드의 삭제와 타입 변경 금지
- 계약 변경은 별도 테스트로 검증
- 호환되지 않는 변경은 신규 경로 또는 명시적
  버전 협상을 별도 설계한 뒤 적용

본 문서만으로 실제 API 버전이 변경되지는 않는다.

## 19. 계약 테스트 계획

후속 구현에서 수행할 검증:

- 기존 15개 엔드포인트 회귀 테스트
- GameResponse 기존 필드 유지 검사
- 신규 필드 스키마 검증
- E01~E30 증거 ID 검증
- 챕터 및 목표 상태 전환 검증
- 스토리 이벤트 중복 방지
- 콘텐츠 버전 고정 및 체크섬 검증
- 미해금 증거 정보 접근 차단
- 내부 콘텐츠 API 인증 실패 검사
- 범인 지목 revision 충돌 검사
- Multi-Agent 출력의 상태 변경 제한
- MCP Tool 접근 권한 검증
- React 어댑터 호환성 검증

## 20. 구현 여부 구분

### 현재 구현된 기능

- FastAPI 게임 API 15개
- 서버 관리 GameState
- 증거 획득 및 범인 지목
- SQLite 게임 세션 저장
- Hybrid RAG 및 NPC 대화
- React API 어댑터

### 신규 구현 예정

- Django 콘텐츠 API
- 콘텐츠 게시 및 ContentRelease
- E01~E30 동적 증거 지원
- CH00~CH04 챕터 상태
- 수사 목표 관리
- storyEvents
- endingKey
- accuseBlockedReason
- Multi-Agent Orchestrator
- MCP Server 및 Client

## 21. 결론

API 계약 v3.0은 기존 FastAPI 게임 API의
하위 호환성을 유지하는 확장 계약이다.

Django는 콘텐츠를 정의하고 게시하며,
FastAPI는 실제 게임 상태와 접근 권한을 관리한다.

Multi-Agent와 MCP는 게임 엔진에 근거와
응답 후보를 제공하고, 최종 판정은 FastAPI가 수행한다.

이 문서는 API 구현을 완료했다는 의미가 아니며,
실제 구현과 통합 테스트는 후속 이슈에서 진행한다.
