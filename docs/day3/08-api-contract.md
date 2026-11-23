
# Day 3 — Django–FastAPI 콘텐츠 API 명세서

## 1. API 개요

Day 3의 API는 두 종류로 구분됩니다.

1. Django 콘텐츠 조회 API: 콘텐츠 관리 정보와 승인된 콘텐츠 제공
2. FastAPI 게임 API: 플레이어별 스토리 이벤트 조회 및 ACK 처리

### 서비스 구분

| 항목 | Django | FastAPI |
|---|---|---|
| 기본 개발 주소 | `http://127.0.0.1:8001` | `http://127.0.0.1:8000` |
| API 역할 | 콘텐츠 원본 조회 | 게임 진행 및 이벤트 전달 |
| 인증 | 서비스 토큰 또는 관리자 세션 | 게임 세션 소유권 |
| 데이터 저장 | Django 콘텐츠 DB | 게임 상태 DB |
| 주요 응답 | 콘텐츠 정의 | 플레이어에게 공개 가능한 정보 |

위 포트는 개발 환경의 기본 설정 예시이며, 실제 실행 설정에 따라 달라질 수 있습니다.

## 2. Django 콘텐츠 API

### 2.1 API 목록

| Method | Endpoint | 설명 | 접근 권한 |
|---|---|---|---|
| GET | `/api/content/cases/{case_id}/overview/` | 사건·챕터 개요 | 관리자 |
| GET | `/api/content/internal/cases/{case_id}/overview/` | 사건·챕터 내부 조회 | 서비스 토큰 |
| GET | `/api/content/internal/cases/{case_id}/readiness/` | 콘텐츠 승인 현황 | 서비스 토큰 |
| GET | `/api/content/internal/cases/{case_id}/scenes/{scene_id}/` | 공개 가능 Scene | 서비스 토큰 |
| GET | `/api/content/internal/cases/{case_id}/evidence/{evidence_id}/requirements/` | 증거 선행 조건 | 서비스 토큰 |
| GET | `/api/content/internal/cases/{case_id}/characters/{character_id}/cards/` | 승인 NPC 카드 | 서비스 토큰 |
| GET | `/api/content/internal/cases/{case_id}/events/{event_key}/` | 승인 StoryEvent | 서비스 토큰 |

### 2.2 서비스 간 인증 헤더

내부 API 호출 시 다음 헤더를 전달합니다.

```http
X-Content-Service-Token: <SERVICE_TOKEN>
Accept: application/json
```

인증 정책:

- 설정된 서비스 토큰과 일치해야 합니다.
- 누락되거나 잘못된 토큰은 403을 반환합니다.
- 내부 API는 관리자 세션만으로 접근할 수 없습니다.
- 서비스 토큰은 최소 32자 이상으로 설정해야 합니다.
- 클라이언트에서 직접 호출하지 않습니다.

## 3. Django 사건 개요 API

### GET `/api/content/internal/cases/{case_id}/overview/`

**목적:** 사건 및 챕터의 기본 관리 정보를 반환합니다.

요청 예시:

```http
GET /api/content/internal/cases/CASE-001/overview/
X-Content-Service-Token: <SERVICE_TOKEN>
```

응답 예시:

```json
{
  "case": {
    "case_id": "CASE-001",
    "title": "테스트 사건",
    "status": "DRAFT"
  },
  "chapters": [
    {
      "code": "CH00",
      "order": 0,
      "title": "프롤로그"
    },
    {
      "code": "CH01",
      "order": 1,
      "title": "첫 번째 챕터"
    }
  ]
}
```

위 응답은 데이터 형식 예시이며 실제 운영 콘텐츠가 아닙니다.

**주의:** 이 API는 내부 관리용 개요 조회입니다. `DRAFT` 상태 정보를 반환할 수 있으므로 플레이어에게 직접 공개하면 안 됩니다.

## 4. Django 콘텐츠 승인 현황 API

### GET `/api/content/internal/cases/{case_id}/readiness/`

**목적:** 콘텐츠 유형별 런타임 승인 여부를 집계합니다.

응답 예시:

```json
{
  "case_id": "CASE-001",
  "resources": {
    "scenes": {
      "total": 30,
      "approved": 0,
      "blocked": 30
    },
    "evidence": {
      "total": 30,
      "approved": 0,
      "blocked": 30
    },
    "npc_cards": {
      "total": 0,
      "approved": 0,
      "blocked": 0
    },
    "objectives": {
      "total": 0,
      "approved": 0,
      "blocked": 0
    }
  }
}
```

수치는 응답 구조 설명을 위한 예시입니다.

| 필드 | 의미 |
|---|---|
| `total` | 전체 콘텐츠 수 |
| `approved` | 런타임 승인 조건 충족 개수 |
| `blocked` | 승인 조건 미충족 개수 |

이 API는 내부 승인 현황을 제공하며, 개별 플레이어의 실제 해금 상태를 계산하지 않습니다.

## 5. Django Scene 조회 API

### GET `/api/content/internal/cases/{case_id}/scenes/{scene_id}/`

**목적:** 플레이어 공개가 허용된 장면을 조회합니다.

공개 조건:

- 사건이 `PUBLISHED`
- Scene이 런타임 승인됨
- Backend 계약 승인 완료
- Scene 공개 범위가 `PLAYER_VISIBLE`

응답 예시:

```json
{
  "scene_id": "SC-0001",
  "chapter": "CH00",
  "title": "테스트 장면",
  "scene_text": "공개 가능한 테스트 장면입니다."
}
```

내부 메타데이터는 응답에 포함하지 않습니다.

미승인 또는 비공개 장면은 404를 반환합니다.

## 6. Django 증거 선행 조건 API

### GET `/api/content/internal/cases/{case_id}/evidence/{evidence_id}/requirements/`

**목적:** 특정 증거의 선행 획득 조건을 반환합니다.

공개 조건:

- 사건이 `PUBLISHED`
- 대상 증거가 런타임 승인됨
- 모든 선행 증거가 런타임 승인됨
- 참조된 증거가 동일한 사건에 속함

응답 예시:

```json
{
  "evidence_id": "E03",
  "prerequisites": ["E01", "E02"],
  "player_unlock_verification_required": true
}
```

`player_unlock_verification_required`가 `true`이므로, Django 응답만으로 증거가 자동 해금되는 것은 아닙니다.

FastAPI에서 플레이어가 해당 선행 증거를 획득했는지 추가로 검증해야 합니다.

## 7. Django NPC 카드 API

### GET `/api/content/internal/cases/{case_id}/characters/{character_id}/cards/`

**목적:** 런타임 승인이 완료된 NPC 카드 목록을 조회합니다.

공개 조건:

- 사건이 `PUBLISHED`
- NPC 카드의 승인 정책이 유효함
- `runtime_enabled=true`
- `disclosure_policy.status=APPROVED`
- `disclosure_policy.allow=true`

응답 예시:

```json
{
  "character_id": "C01",
  "cards": [
    {
      "card_id": "K-C01-01",
      "card_type": "KNOWLEDGE",
      "content": "공개 승인된 테스트 카드입니다."
    }
  ]
}
```

이 API는 게임 엔진 내부용입니다.

Django에서 승인된 카드라도 FastAPI의 기존 NPC 지식 공개 정책과 게임 상태 검증을 통과해야 플레이어에게 사용할 수 있습니다.

## 8. Django StoryEvent API

### GET `/api/content/internal/cases/{case_id}/events/{event_key}/`

**목적:** 런타임 승인을 받은 StoryEvent 정의를 반환합니다.

공개 조건:

- 사건이 `PUBLISHED`
- 이벤트 런타임 승인 완료
- Backend 계약 승인 완료
- 지원하는 트리거 유형
- 유효한 증거 조건
- 허용된 payload 필드만 포함

현재 API에서 지원하는 트리거 유형:

`EVIDENCE_COLLECTED`

응답 예시:

```json
{
  "event_key": "EVT-CH01-901",
  "chapter": "CH01",
  "trigger_type": "EVIDENCE_COLLECTED",
  "required_evidence_ids": ["E19"],
  "title": "테스트 이벤트",
  "text": "테스트 스토리 이벤트입니다."
}
```

`EVT-CH01-901`은 테스트에서 사용한 가상 이벤트 식별자입니다. 운영용 StoryEvent로 승인된 것이 아닙니다.

### 입력 제약

| 필드 | 제약 |
|---|---|
| `event_key` | `EVT-CH01-001` 형식 |
| `chapter` | CH00~CH04 |
| `trigger_type` | 현재 `EVIDENCE_COLLECTED` |
| `required_evidence_ids` | E01~E30, 1~30개 |
| `title` | 1~120자 |
| `text` | 최대 5,000자 |

## 9. FastAPI StoryEvent API

### 9.1 엔드포인트 목록

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/api/games/{session_id}/story-events/pending` | 미확인 이벤트 목록 |
| GET | `/api/games/{session_id}/story-events/{event_key}` | 이벤트 상세 |
| POST | `/api/games/{session_id}/story-events/{event_key}/ack` | 이벤트 확인 처리 |

모든 API는 기존 게임 세션 소유권 검사를 적용합니다.

### 9.2 미확인 이벤트 조회

#### GET `/api/games/{session_id}/story-events/pending`

응답 예시:

```json
{
  "items": [
    {
      "eventKey": "EVT-CH01-901",
      "chapter": "CH01",
      "title": "테스트 이벤트",
      "text": "테스트 스토리 이벤트입니다."
    }
  ]
}
```

승인되거나 해금된 이벤트가 없으면 다음과 같이 반환합니다.

```json
{
  "items": []
}
```

이벤트 바인딩이 설정되지 않은 기본 상태에서는 빈 목록을 반환합니다.

### 9.3 이벤트 상세 조회

#### GET `/api/games/{session_id}/story-events/{event_key}`

응답 예시:

```json
{
  "eventKey": "EVT-CH01-901",
  "chapter": "CH01",
  "title": "테스트 이벤트",
  "text": "테스트 스토리 이벤트입니다."
}
```

다음 경우에는 이벤트 본문을 반환하지 않습니다.

- 세션 소유권 없음
- 서버 이벤트 바인딩 없음
- 이벤트가 큐에 존재하지 않음
- 필수 증거 미획득
- 챕터 미해금
- Django 콘텐츠 승인 실패
- 이미 ACK한 이벤트

### 9.4 이벤트 확인 처리

#### POST `/api/games/{session_id}/story-events/{event_key}/ack`

응답 예시:

```json
{
  "eventKey": "EVT-CH01-901",
  "acknowledged": true,
  "created": true,
  "revision": 3
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `eventKey` | string | 이벤트 식별자 |
| `acknowledged` | boolean | ACK 성공 여부 |
| `created` | boolean | 신규 ACK 생성 여부 |
| `revision` | integer | 저장된 게임 상태 버전 |

중복 ACK 시 `created=false`를 반환합니다.

## 10. FastAPI 오류 응답 규격

| HTTP 코드 | 주요 발생 조건 |
|---|---|
| 404 | 세션 소유권 없음, 이벤트 없음, 미승인 또는 미해금 |
| 409 | 게임 상태 revision 충돌 |
| 503 | Django 연결 실패, 타임아웃, 응답 계약 오류, 서비스 미설정 |

### 503 예시

```json
{
  "detail": "Content service unavailable"
}
```

### 404 예시

```json
{
  "detail": "Event not found"
}
```

### 409 예시

```json
{
  "detail": "Game state changed"
}
```

## 11. 데이터 계약 검증

FastAPI는 Django의 HTTP 응답을 Pydantic 모델로 검증합니다.

주요 검증 항목:

- 예상하지 않은 필드 거부
- 필수 필드 누락 거부
- 잘못된 JSON 거부
- 요청 ID와 응답 ID 불일치 거부
- 중복 증거 및 카드 ID 거부
- 잘못된 챕터·이벤트 ID 거부
- 응답 크기 제한 초과 거부

내부 서비스 오류 메시지 또는 인증 토큰은 플레이어 응답에 포함하지 않습니다.

## 12. 주요 테스트 결과

| 항목 | 결과 |
|---|---|
| Django API 인증·권한 신규 테스트 | 15 PASS |
| FastAPI 장애 대응 신규 테스트 | 10 PASS |
| StoryEvent HTTP 테스트 | 전체 회귀에서 통과 |
| Django 전체 테스트 | 228 PASS |
| FastAPI 전체 테스트 | 1,734 PASS / 9 SKIP |

## 13. API 계약의 제한사항

현재 구현은 콘텐츠 관리와 게임 엔진 간 안전한 조회 및 전달 기반입니다.

다음 기능은 별도 작업이 필요합니다.

- 전체 StoryEvent의 실제 운영 바인딩
- 모든 트리거 유형의 런타임 처리
- 실제 게임 행동과 자동 이벤트 큐 등록 연계
- 콘텐츠 버전 변경에 따른 실시간 동기화
- 실제 독립 프로세스 간 네트워크 E2E

## 14. 결론

Django는 승인된 콘텐츠를 제공하고, FastAPI는 플레이어별 접근 조건을 검증합니다.

이중 검증 구조를 통해 콘텐츠의 관리 권한과 플레이어의 해금 상태를 분리했으며, 테스트에서 인증 오류, 데이터 계약 위반 및 서비스 장애에 대한 차단 동작을 확인했습니다.
