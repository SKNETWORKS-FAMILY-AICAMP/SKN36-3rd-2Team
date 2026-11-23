
# Day 3 — Django–FastAPI 콘텐츠 통합 테스트 및 개발 문서

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 프로젝트 | 마지막 기록: 졸업하지 못한 밤 |
| 개발 단계 | 4차 단위 프로젝트 — Day 3 |
| 관련 EPIC | #116 |
| 콘텐츠 통합 구현 | #120 |
| 통합 테스트 및 문서화 | #121 |
| 기준 커밋 | `be0eeba` |
| 작업 브랜치 | `test/121-day3-content-integration` |
| 콘텐츠 관리 | Django 5.2.19 / DRF |
| 게임 엔진 | FastAPI / Pydantic |
| 프론트엔드 | React / TypeScript |

### 개발 목적

기존 FastAPI 기반 AI 추리 게임에 Django 콘텐츠 관리 시스템을 연동하여, 콘텐츠 데이터와 플레이어의 게임 진행 상태를 분리하고 안전한 콘텐츠 공개 체계를 구축합니다.

Django는 콘텐츠 원본과 승인 상태를 관리하고, FastAPI는 플레이어별 진행 상태와 콘텐츠 해금 여부를 판정합니다.

## 2. 주요 개발 결과

### 2.1 Django 콘텐츠 관리

- CASE-001 콘텐츠 ORM 모델 구성
- 챕터, 장면, NPC, 증거, 이벤트 관계 정의
- 콘텐츠 유효성 및 참조 무결성 검증
- 콘텐츠 게시 상태 관리
- StoryEvent 런타임 승인 메타데이터 추가
- Django REST Framework 내부 조회 API 구축

### 2.2 데이터 Import

- 증거 검토표 기반 StoryEvent Import
- V3 STORY 매핑 기반 StoryEvent Import
- CSV 컬럼 및 데이터 개수 검증
- 중복 ID 및 잘못된 참조 검사
- Dry Run 지원
- 동일 데이터 재적재 시 멱등 처리
- 트랜잭션을 통한 오류 발생 시 전체 롤백
- 검토 전 콘텐츠의 자동 활성화 방지

### 2.3 FastAPI 통합

- Django 콘텐츠 전용 HTTP 클라이언트 구현
- 서비스 토큰 기반 내부 인증
- Pydantic 기반 API 응답 검증
- 콘텐츠 접근 조건과 게임 진행 상태 연동
- 증거 및 챕터 공개 정책 검증
- Django 장애 및 타임아웃 처리
- 기존 게임 API와의 호환성 유지

### 2.4 StoryEvent 시스템

- 증거 획득 조건에 따른 이벤트 검증
- 챕터·증거·게임 단계별 공개 조건 확인
- StoryEvent 큐 관리
- 이벤트 상세 및 미확인 목록 조회
- 사용자 확인(ACK) 처리
- SQLite revision CAS를 통한 동시성 제어
- ACK 중복 실행 시 멱등 처리
- 미승인 콘텐츠의 기본 공개 차단

### 2.5 React 프론트엔드

- StoryEvent 전용 API 클라이언트
- StoryEvent 표시 오버레이
- 플레이어 확인 버튼과 ACK 연동
- 이벤트 확인 상태에 따른 UI 처리
- 기존 게임 화면과의 연결

## 3. 시스템 구성

| 구성 요소 | 역할 |
|---|---|
| Django | 콘텐츠 원본 및 승인 상태 관리 |
| DRF | 내부 콘텐츠 API 제공 |
| FastAPI | 게임 진행, 콘텐츠 접근 제어, StoryEvent 전달 |
| Django SQLite | 콘텐츠 관리 데이터 저장 |
| FastAPI SQLite | 세션, 진행 상태, 이벤트 ACK 저장 |
| React | 게임 화면 및 스토리 이벤트 표시 |
| Qdrant | 기존 벡터 검색 |
| Neo4j | 기존 인물·증거 관계 그래프 |
| Hybrid RAG | NPC 대화용 기존 검색 구조 |

## 4. 최종 테스트 결과

| 검증 항목 | 최종 결과 |
|---|---|
| Django 전체 테스트 | **228 PASS** |
| FastAPI 전체 테스트 | **1,734 PASS / 9 SKIP** |
| Django Migration 검사 | PASS |
| React 프로덕션 빌드 | PASS |
| 스포일러 검사 | PASS |
| Issue #121 신규 테스트 | **49 PASS** |
| 실행한 테스트의 실패 건수 | **0건** |

### 신규 테스트 구성

| 분류 | 신규 테스트 |
|---|---:|
| 검토 완료 이벤트 Import | 10 |
| V3 StoryEvent Import | 14 |
| DRF 인증·권한 통합 | 15 |
| FastAPI 장애 대응 | 10 |
| **합계** | **49** |

## 5. 실행 및 테스트 방법

### Django

```powershell
cd backend/django_service
uv sync --locked
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
```

### FastAPI

```powershell
cd backend
uv sync --locked
uv run pytest -q
```

### React

```powershell
cd frontend
npm ci
npm run build
npm run spoiler
```

각 명령어는 프로젝트 루트 기준 해당 디렉터리에서 실행합니다.

## 6. 개발 문서 목록

| 문서 | 설명 |
|---|---|
| [01-test-results.md](01-test-results.md) | 테스트 항목 및 최종 검증 결과 |
| [02-architecture.md](02-architecture.md) | 시스템 구성 및 데이터 흐름 |
| [03-erd.md](03-erd.md) | Django ORM 모델 및 관계 |
| [04-api-contract.md](04-api-contract.md) | Django·FastAPI API 명세 |
| [05-integration-risks.md](05-integration-risks.md) | 미완료 기능, 장애 위험, 후속 작업 |

## 7. 현재 구현 범위

**완료**

- Django 콘텐츠 모델 및 API
- Import 검증 로직
- 서비스 간 인증 및 데이터 계약
- FastAPI 콘텐츠 연동 기반
- StoryEvent 조회 및 ACK
- 자동화 통합 테스트
- 전체 회귀 테스트

**미완료 또는 별도 검증 필요**

- 실제 CASE-001 정본 콘텐츠 최종 승인
- 실제 스토리 이벤트의 자동 발동 연결
- NPC 반응 및 스토리 연출 연계
- 독립 Django·FastAPI 프로세스 간 실제 네트워크 E2E
- 운영 환경 DB Migration 적용 검증
- 전체 게임 플레이 E2E
- Multi-Agent 및 MCP 확장

## 8. 개발 원칙

1. 미승인 콘텐츠는 기본적으로 공개하지 않습니다.
2. Django의 콘텐츠 승인과 FastAPI의 플레이어 해금을 별도로 검증합니다.
3. 플레이어에게 내부 API 토큰이나 콘텐츠 메타데이터를 전달하지 않습니다.
4. 콘텐츠 Import는 기본적으로 Dry Run으로 실행합니다.
5. 실제 정본 데이터는 검토와 승인 전까지 활성화하지 않습니다.
6. 테스트는 격리된 테스트 DB와 모의 HTTP 응답을 사용합니다.
7. 검증하지 않은 기능은 완료로 표기하지 않습니다.

## 9. 결론

Day 3에서는 Django 콘텐츠 관리 시스템과 FastAPI 게임 엔진 사이의 콘텐츠 조회, 승인 검증 및 StoryEvent 전달 기반을 구현했습니다.

Issue #121의 자동화 테스트 49개를 추가했으며, Django 228개 및 FastAPI 1,734개 테스트가 통과했습니다.

다만 실제 콘텐츠 승인 및 전체 플레이 시나리오 연동은 후속 작업으로 남아 있습니다.
