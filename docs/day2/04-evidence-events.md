# Day 2 — Issue #104: Evidence·StoryEvent ORM 구현

## 1. 작업 개요

Django 기반 콘텐츠 관리 시스템에 증거, 증거 선행 관계, 스토리 이벤트 모델을 추가했습니다.

기존 Case·Chapter·Character 모델을 기반으로 사건별 증거 데이터와 스토리 이벤트를 구조화하고, 증거 해금 조건의 데이터 무결성을 검증하는 서비스 계층을 구현했습니다.

**작업 브랜치:** `feature/104-evidence-events`

**관련 이슈:** #104

## 2. 구현 모델

| 모델 | DB 테이블 | 역할 |
|---|---|---|
| Evidence | content_evidence | 사건별 증거 정보 |
| EvidencePrerequisite | content_evidence_prerequisite | 증거 간 선행 조건 |
| StoryEvent | content_storyevent | 챕터별 스토리 이벤트 |

### 2.1 Evidence

- Case와 1:N 관계
- Character와 선택적 N:1 관계
- 증거 ID `E01~E30` 검증
- 사건별 증거 ID UNIQUE 제약
- 증거 점수는 0 이상
- 내부 메타데이터 JSON 저장
- 다른 사건의 NPC를 관련 인물로 설정하는 행위 검증

### 2.2 EvidencePrerequisite

- Evidence 간 자기참조 M:N 관계
- 명시적 Through 모델 사용
- 동일한 선행 관계의 중복 저장 방지
- 증거 자기참조 차단
- 서로 다른 사건의 증거 연결 차단
- 그래프 탐색 기반 순환 참조 검증

선행 관계는 `dependent → prerequisite` 방향으로 저장합니다.

예: E03이 E02를 필요로 하고, E02가 E01을 필요로 하는 관계는 허용합니다. E01이 다시 E03을 필요로 하는 관계는 순환이므로 거부합니다.

### 2.3 StoryEvent

- Chapter와 1:N 관계
- 이벤트 키 형식: `EVT-CH01-001`
- 이벤트 키 전역 UNIQUE
- 발동 조건과 출력 콘텐츠를 JSONField로 관리
- 소속 챕터와 이벤트 키의 챕터 코드 일치 여부 검증

지원 트리거:

| 트리거 | 의미 |
|---|---|
| EVIDENCE_COLLECTED | 증거 획득 |
| NPC_UNLOCKED | NPC 해금 |
| CHAPTER_STARTED | 챕터 시작 |
| DIALOGUE_COMPLETED | 대화 완료 |

Django는 이벤트 정의를 관리하며, 실제 이벤트 발동 여부와 플레이어 진행 상태는 FastAPI 게임 엔진에서 처리합니다.

## 3. 데이터베이스 변경

**Migration:** `0002_evidence_evidenceprerequisite_evidence_prerequisites_and_more.py`

추가 테이블:

- `content_evidence`
- `content_evidence_prerequisite`
- `content_storyevent`

주요 제약조건:

| 제약조건 | 목적 |
|---|---|
| unique_evidence_case_id | 사건별 증거 ID 중복 방지 |
| unique_evidence_prerequisite | 증거 선행 관계 중복 방지 |
| evidence_prereq_no_self | 자기참조 방지 |
| storyevent_valid_trigger | 정의된 트리거만 저장 |

Migration 적용 결과: **PASS**

Django 시스템 검사 결과: **PASS**

## 4. Service Layer

**파일:** `backend/django_service/apps/content/services.py`

**함수:** `create_evidence_prerequisite()`

처리 흐름:

1. 증거 ID 입력값 검증
2. DB 트랜잭션 시작
3. 대상 증거 존재 여부 확인
4. 사건 소속 일치 여부 확인
5. 모델 비즈니스 규칙 검증
6. 선행 관계 저장
7. 정상 종료 시 트랜잭션 커밋

`transaction.atomic()`을 사용하여 저장 과정에서 오류가 발생할 경우 해당 트랜잭션의 변경을 롤백합니다.

## 5. 자동화 테스트 결과

| 테스트 구분 | 실행 개수 | 결과 |
|---|---:|---|
| Case·Chapter·Character | 8 | PASS |
| Evidence·StoryEvent | 14 | PASS |
| 증거 관계 저장 서비스 | 8 | PASS |
| Health API | 3 | PASS |
| **전체** | **33** | **PASS** |

- 전체 실패: 0건
- 전체 오류: 0건
- 측정된 전체 테스트 실행 시간: 0.179초

테스트 명령어: `uv run python manage.py test --verbosity 2`

## 6. 보안 및 무결성 고려사항

- ForeignKey와 UNIQUE, CHECK 제약조건을 사용해 기본적인 데이터 무결성을 확보했습니다.
- `full_clean()`을 통해 증거 ID, 사건 소속, 순환 관계 등을 검증합니다.
- 직접 `objects.create()`, `bulk_create()`, M:N `.add()` 등을 사용하면 일부 Python 검증이 실행되지 않을 수 있습니다.
- 관계 생성은 검증된 서비스 함수를 사용하도록 통일해야 합니다.
- SQLite에서는 `select_for_update()`가 실제 행 잠금을 제공하지 않으므로 동시 쓰기 경쟁에 대한 추가 검증이 필요합니다.
- JSONField의 DB 검증은 JSON 문법을 확인하며, 비즈니스 스키마 검증과는 구분됩니다.
- 이벤트의 조건 JSON 구조는 향후 API 계약 및 스키마 검증 단계에서 구체화해야 합니다.

## 7. 기존 시스템 영향

- FastAPI 게임 상태 저장 구조 변경 없음
- Qdrant 벡터 DB 변경 없음
- Neo4j 관계 그래프 변경 없음
- Django 콘텐츠 관리 DB에 신규 테이블 3개 추가

## 8. 완료 현황 및 후속 작업

**Issue #104 구현 및 단일 요청 테스트 완료**

후속 이슈:

- #105 ContentRelease 모델 구현
- #106 Django Admin 콘텐츠 관리 기능
- #107 통합 테스트 및 개발 문서 검증

향후 FastAPI 연동 단계에서 콘텐츠 공개 권한과 실제 증거 해금 상태를 별도 검증해야 합니다.