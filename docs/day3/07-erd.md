
# Day 3 — Django 콘텐츠 데이터베이스 ERD

## 1. 데이터베이스 개요

Day 3에서 사용한 Django 콘텐츠 ORM은 총 **13개 모델**로 구성되어 있습니다.

콘텐츠 DB는 사건 원본, 챕터, NPC, 증거, 스토리 이벤트, 게시 상태를 관리합니다.

FastAPI의 플레이어별 진행 상태는 별도의 SQLite 저장소에서 관리합니다.

## 2. 전체 ERD

```mermaid
erDiagram
    Case ||--o{ Chapter : contains
    Case ||--o{ Character : contains
    Case ||--o{ Scene : contains
    Case ||--o{ Evidence : contains
    Case ||--o{ ContentRelease : publishes

    Chapter ||--o{ Scene : contains
    Chapter ||--o{ StoryEvent : has
    Chapter ||--o{ Objective : defines

    Character ||--o{ NPCCard : owns
    Character ||--o{ NPCDialogueTrigger : owns
    Character ||--o{ CharacterRelationship : originates
    Character |o--o{ Evidence : holds

    Evidence ||--o{ EvidenceLink : from
    Evidence ||--o{ EvidenceLink : to

    Evidence ||--o{ EvidencePrerequisite : dependent
    Evidence ||--o{ EvidencePrerequisite : prerequisite

    Case {
        bigint id PK
        varchar case_id UK
        varchar title
        text description
        varchar status
    }

    Chapter {
        bigint id PK
        bigint case_id FK
        varchar code
        int order
        varchar title
        text summary
        json metadata
    }

    Scene {
        bigint id PK
        bigint case_id FK
        bigint chapter_id FK
        varchar scene_id
        varchar title
        text scene_text
        varchar visibility
        json metadata
    }

    Character {
        bigint id PK
        bigint case_id FK
        varchar character_id
        varchar name
        text profile
        json metadata
    }

    Evidence {
        bigint id PK
        bigint case_id FK
        bigint holder_id FK
        varchar evidence_id
        varchar name
        int score
        json metadata
    }

    StoryEvent {
        bigint id PK
        bigint chapter_id FK
        varchar event_key UK
        varchar trigger_type
        json conditions
        json payload
        json metadata
    }

    EvidenceLink {
        bigint id PK
        bigint from_evidence_id FK
        bigint to_evidence_id FK
        varchar relationship
        varchar resulting_inference
        boolean needs_canon_approval
        boolean is_active
        json metadata
    }

    EvidencePrerequisite {
        bigint id PK
        bigint dependent_id FK
        bigint prerequisite_id FK
    }

    NPCCard {
        bigint id PK
        bigint character_id FK
        varchar card_id
        varchar card_type
        text content
        json disclosure_policy
        json metadata
    }

    NPCDialogueTrigger {
        bigint id PK
        bigint character_id FK
        varchar trigger_id UK
        int stage
        varchar trigger_type
        varchar output_mode
        text response_text
        varchar condition_key
        int output_order
        boolean is_active
        json metadata
    }

    CharacterRelationship {
        bigint id PK
        bigint source_character_id FK
        varchar target_type
        varchar target_id
        text relationship
        int public_from_stage
        boolean is_active
        json metadata
    }

    Objective {
        bigint id PK
        bigint chapter_id FK
        varchar objective_id
        text player_goal
        json hints
        json completion_rule
        boolean is_active
        json metadata
    }

    ContentRelease {
        bigint id PK
        bigint case_id FK
        varchar version
        json manifest
        varchar checksum
        datetime published_at
    }
```

**참고:** 다이어그램의 `varchar`, `int`, `json`은 이해를 돕기 위한 논리 타입입니다. 실제 SQLite 저장 타입과 Django 필드 정의는 `models.py`를 기준으로 합니다. 또한 `UK` 표기가 없는 복합 UNIQUE 제약조건은 아래에서 별도로 설명합니다.

## 3. 모델별 역할

| 모델 | 실제 DB 테이블 | 주요 역할 |
|---|---|---|
| Case | `content_case` | 사건 정의 및 상태 |
| Chapter | `content_chapter` | 챕터 순서 및 정보 |
| Scene | `content_scene` | 장면 원고 및 공개 범위 |
| Character | `content_character` | NPC 정보 |
| Evidence | `content_evidence` | 증거 정의 및 보유 NPC |
| EvidencePrerequisite | `content_evidence_prerequisite` | 증거 선행 관계 |
| EvidenceLink | `content_evidence_link` | 증거 간 추론 관계 |
| StoryEvent | `content_storyevent` | 이벤트 조건 및 출력 콘텐츠 |
| NPCCard | `content_npc_card` | NPC 지식·잡담 카드 |
| NPCDialogueTrigger | `content_npc_dialogue_trigger` | NPC 대화 발동 조건 |
| CharacterRelationship | `content_character_relationship` | NPC 간 관계 및 외부 대상 |
| Objective | `content_objective` | 플레이어 목표와 힌트 |
| ContentRelease | `content_contentrelease` | 콘텐츠 게시 버전 |

## 4. 주요 테이블 설명

### 4.1 Case

사건의 기본 정보를 저장합니다.

주요 컬럼:

- `case_id`: 사건 식별자 (`CASE-001`)
- `title`: 사건 제목
- `description`: 공개 사건 소개
- `status`: 사건 관리 상태

상태값:

- `DRAFT`: 작성 중
- `REVIEW`: 검토 중
- `PUBLISHED`: 게시됨
- `ARCHIVED`: 보관됨

`case_id`는 UNIQUE입니다.

### 4.2 Chapter

사건의 챕터를 관리합니다.

주요 컬럼:

- `case_id`: 소속 사건 FK
- `code`: 챕터 코드 (`CH00`~`CH04`)
- `order`: 챕터 순서
- `title`: 챕터 제목
- `summary`: 챕터 요약
- `metadata`: 추가 정보

제약조건:

- `(case, code)` UNIQUE
- `(case, order)` UNIQUE

### 4.3 Scene

스토리 장면 원고와 공개 조건을 관리합니다.

주요 컬럼:

- `case_id`: 소속 사건
- `chapter_id`: 소속 챕터
- `scene_id`: 장면 ID
- `title`: 장면 제목
- `scene_text`: 장면 원고
- `visibility`: 공개 범위
- `metadata`: 추가 정보

공개 범위:

| 값 | 의미 |
|---|---|
| `ENGINE_ONLY` | 게임 엔진 전용 |
| `NPC_KNOWLEDGE` | NPC 지식 전용 |
| `UNLOCKED_ONLY` | 해금 조건 필요 |
| `PLAYER_VISIBLE` | 기본 공개 장면 |

제약조건:

- `(case, scene_id)` UNIQUE
- Scene과 Chapter는 동일 Case에 속해야 함

현재 플레이어용 Scene 내부 API는 게시 및 런타임 승인 조건을 충족한 `PLAYER_VISIBLE` 장면만 반환합니다.

### 4.4 Character

사건에 등장하는 NPC를 관리합니다.

주요 컬럼:

- `case_id`: 소속 사건
- `character_id`: NPC 식별자
- `name`: NPC 이름
- `profile`: 공개 프로필
- `metadata`: 내부 정보

제약조건:

- `(case, character_id)` UNIQUE

### 4.5 Evidence

증거와 관련 NPC를 관리합니다.

주요 컬럼:

- `case_id`: 소속 사건
- `evidence_id`: 증거 식별자
- `name`: 증거 이름
- `holder_id`: 관련 NPC
- `score`: 증거 점수
- `metadata`: 증거 메타데이터

제약조건:

- `(case, evidence_id)` UNIQUE
- 증거와 보유 NPC는 동일 사건에 속해야 함
- `score`는 NULL 허용

### 4.6 EvidencePrerequisite

증거 획득을 위한 선행 관계를 저장합니다.

- `dependent_id`: 선행 조건이 필요한 증거
- `prerequisite_id`: 먼저 획득해야 하는 증거

검증 기준:

- 자기 자신을 선행 조건으로 지정할 수 없음
- 서로 다른 사건의 증거를 연결할 수 없음
- 순환 관계를 생성할 수 없음
- 동일 관계 중복 등록 불가

예시:

`E02`가 `E01`을 요구한다면, `E01` 획득 후 `E02` 해금 조건을 평가합니다.

### 4.7 EvidenceLink

증거 사이의 추론 관계를 저장합니다.

주요 컬럼:

- `from_evidence_id`
- `to_evidence_id`
- `relationship`
- `resulting_inference`
- `needs_canon_approval`
- `is_active`
- `metadata`

제약조건:

- 동일 증거 간 자기참조 불가
- 서로 다른 사건의 증거 관계 불가
- `(from_evidence, to_evidence, relationship)` UNIQUE
- 정본 승인이 필요한 관계는 활성화 불가

### 4.8 StoryEvent

증거 획득 등에 따라 발생하는 스토리 이벤트 정의를 저장합니다.

주요 컬럼:

- `chapter_id`: 소속 챕터
- `event_key`: 이벤트 ID
- `trigger_type`: 이벤트 발동 유형
- `conditions`: 발동 조건 JSON
- `payload`: 출력 콘텐츠 JSON
- `metadata`: 런타임 승인 메타데이터

지원되는 트리거 정의:

- `EVIDENCE_COLLECTED`
- `NPC_UNLOCKED`
- `CHAPTER_STARTED`
- `DIALOGUE_COMPLETED`

단, 현재 승인된 이벤트 조회 API의 런타임 계약은 `EVIDENCE_COLLECTED`만 허용합니다.

이벤트 ID는 `EVT-CH01-001` 형식을 따르며, 이벤트 키와 소속 챕터 코드의 일치 여부를 검사합니다.

### 4.9 NPCCard

NPC의 지식 및 잡담 콘텐츠를 저장합니다.

주요 컬럼:

- `character_id`
- `card_id`
- `card_type`
- `content`
- `disclosure_policy`
- `metadata`

카드 유형:

- `KNOWLEDGE`
- `SMALLTALK`

제약조건:

- `(character, card_id)` UNIQUE
- 카드 ID와 NPC ID의 일치 여부 검사
- 카드 유형과 ID 접미사 일치 여부 검사

### 4.10 NPCDialogueTrigger

NPC의 대화 트리거를 관리합니다.

주요 컬럼:

- `character_id`
- `trigger_id`
- `stage`
- `trigger_type`
- `output_mode`
- `response_text`
- `condition_key`
- `output_order`
- `is_active`
- `metadata`

대화 단계는 1~3만 허용합니다.

`trigger_id`는 전역 UNIQUE이며, NPC 및 트리거 유형별 조회 인덱스가 있습니다.

### 4.11 CharacterRelationship

NPC가 다른 NPC, 증거, 외부 인물과 맺는 관계를 관리합니다.

주요 컬럼:

- `source_character_id`
- `target_type`
- `target_id`
- `relationship`
- `public_from_stage`
- `is_active`
- `metadata`

`target_type`:

- `npc`
- `evidence`
- `person`

`target_id`는 다형적 참조 식별자이며, 일반 ForeignKey가 아닙니다. NPC 및 증거 대상에 대해서는 모델 검증 단계에서 동일 사건의 대상 존재 여부를 확인합니다.

### 4.12 Objective

플레이어의 목표와 힌트를 관리합니다.

주요 컬럼:

- `chapter_id`
- `objective_id`
- `player_goal`
- `hints`
- `completion_rule`
- `is_active`
- `metadata`

제약조건:

- `(chapter, objective_id)` UNIQUE
- 힌트는 최대 3개
- 완료 조건이 없는 목표는 활성화 불가

### 4.13 ContentRelease

게시 버전과 콘텐츠 스냅샷을 관리합니다.

주요 컬럼:

- `case_id`
- `version`
- `manifest`
- `checksum`
- `published_at`

제약조건:

- `(case, version)` UNIQUE
- 버전 형식: `v1.0.0`
- checksum 형식: `sha256:` + 64자리 16진수
- 게시 후 일반적인 수정 및 삭제 차단

## 5. 주요 관계와 데이터 무결성

| 관계 | 카디널리티 | 주요 제약 |
|---|---|---|
| Case → Chapter | 1:N | 사건별 코드·순서 UNIQUE |
| Case → Scene | 1:N | 사건별 Scene ID UNIQUE |
| Case → Character | 1:N | 사건별 NPC ID UNIQUE |
| Case → Evidence | 1:N | 사건별 Evidence ID UNIQUE |
| Chapter → StoryEvent | 1:N | 이벤트 키와 챕터 일치 |
| Chapter → Objective | 1:N | 챕터별 목표 ID UNIQUE |
| Character → NPCCard | 1:N | NPC별 카드 ID UNIQUE |
| Evidence → EvidenceLink | 1:N | 관계 중복 및 승인 조건 |
| Evidence → EvidencePrerequisite | 1:N | 자기참조·순환 금지 |
| Case → ContentRelease | 1:N | 사건별 게시 버전 UNIQUE |

## 6. Migration 구조

Day 3 기능에 포함된 Migration:

`backend/django_service/apps/content/migrations/0006_story_event_runtime_approval.py`

### 변경 내용

StoryEvent에 다음 필드를 추가합니다.

```python
metadata = models.JSONField(
    default=dict,
    blank=True,
)
```

이 필드는 이벤트의 런타임 승인 상태와 출처 정보를 관리하는 데 사용됩니다.

### 검증 명령어

```powershell
cd backend/django_service
uv run python manage.py makemigrations --check --dry-run
```

검증 결과:

```text
No changes detected
```

이는 모델 정의에 필요한 추가 Migration 파일이 없다는 의미입니다.

실제 DB 적용 여부를 확인하려면 다음 명령어를 별도로 실행해야 합니다.

```powershell
uv run python manage.py showmigrations content
```

운영 환경 Migration 적용 및 롤백은 이번 자동화 테스트의 범위가 아닙니다.

## 7. FastAPI 게임 상태 DB와 분리

Django 콘텐츠 DB와 FastAPI 게임 상태 DB는 별도로 관리됩니다.

### Django 콘텐츠 DB

- 사건 원본
- 챕터 및 장면
- NPC 및 증거
- 증거 추론 관계
- StoryEvent 정의
- 콘텐츠 게시 상태

### FastAPI 게임 상태 DB

- 게임 세션
- 플레이어 진행 상태
- 획득 증거
- 해금 챕터
- StoryEvent 큐
- ACK 이력
- revision

두 DB 사이의 관계는 직접적인 SQL ForeignKey가 아니라 **서비스 API와 식별자 검증**을 통해 연결됩니다.

## 8. 결론

Django ORM 13개 모델을 이용하여 콘텐츠 정의와 승인·게시 정보를 관리하고, FastAPI는 플레이어별 게임 상태를 관리하도록 역할을 분리했습니다.

이번 단계에서는 ORM 참조 무결성, Import 트랜잭션, 서비스 API와 이벤트 전달 로직을 검증했습니다.
