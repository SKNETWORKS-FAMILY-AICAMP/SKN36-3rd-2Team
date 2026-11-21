# Day 2 — Issue #105: ContentRelease ORM 구현

## 1. 작업 개요

Django 콘텐츠 관리 시스템에 `ContentRelease` 모델을 추가하여 사건별 콘텐츠 게시 버전과 스냅샷을 관리할 수 있도록 구현했습니다.

게시 기록의 중복 생성, 일반적인 ORM 수정 및 삭제를 방지하고 자동화 테스트를 통해 동작을 검증했습니다.

- **Issue:** #105
- **Branch:** `feature/105-content-release`
- **Framework:** Django 5.2
- **Python:** 3.13

## 2. ContentRelease 데이터 모델

**DB 테이블:** `content_contentrelease`

| 필드 | 타입 | 설명 |
|---|---|---|
| id | BigAutoField | 기본키 |
| case | ForeignKey | 게시 대상 사건 |
| version | CharField(30) | 게시 버전 |
| manifest | JSONField | 콘텐츠 스냅샷 |
| checksum | CharField(71) | SHA-256 형식의 체크섬 |
| published_at | DateTimeField | 게시 시각 |

### 관계

- Case 1 : N ContentRelease
- `on_delete=PROTECT` 적용
- `UNIQUE(case, version)` 적용

### 검증 규칙

- 버전 형식: `v1.0.0`
- 체크섬 형식: `sha256:` + 소문자 16진수 64자리
- manifest는 JSON 객체여야 함
- 같은 사건에서 동일한 버전 중복 생성 불가

## 3. 게시 버전 불변성

게시된 버전은 수정하는 대신 새로운 버전으로 생성하는 정책을 적용했습니다.

### 모델 보호

- `save()` 재정의를 통한 기존 레코드 수정 차단
- `delete()` 재정의를 통한 개별 삭제 차단
- `full_clean()` 기반 입력값 검증

### QuerySet 보호

`ContentReleaseQuerySet`을 정의하여 다음 작업을 차단했습니다.

| 작업 | 정책 |
|---|---|
| update() | 차단 |
| delete() | 차단 |
| bulk_create() | 차단 |
| bulk_update() | 차단 |
| update_or_create()로 기존 행 변경 | 모델 save()에서 차단 |

단, 직접 SQL이나 별도의 DB 연결을 통한 변경까지 보호하는 것은 아닙니다.

## 4. Database Migration

**Migration:** `0003_contentrelease.py`

신규 생성 테이블:

`content_contentrelease`

적용한 주요 제약조건:

- `unique_release_case_version`
- `case_id` ForeignKey
- manifest JSON 유효성 검사
- `published_at` NOT NULL

**Migration 적용 결과:** PASS

**Django 시스템 검사:** PASS

## 5. 자동화 테스트 결과

### ContentRelease 테스트

| 검증 항목 | 결과 |
|---|---|
| 정상 게시 기록 생성 | PASS |
| 동일 사건 버전 중복 방지 | PASS |
| 다른 사건에서 같은 버전 허용 | PASS |
| 잘못된 버전 형식 거부 | PASS |
| 잘못된 체크섬 형식 거부 | PASS |
| 잘못된 manifest 구조 거부 | PASS |
| 인스턴스 수정 차단 | PASS |
| 인스턴스 삭제 차단 | PASS |
| QuerySet.update 차단 | PASS |
| QuerySet.delete 차단 | PASS |
| bulk_create 차단 | PASS |
| bulk_update 차단 | PASS |
| update_or_create 변경 차단 | PASS |
| Case 삭제 보호 | PASS |

### 전체 회귀 테스트

| 테스트 구분 | 개수 | 결과 |
|---|---:|---|
| 기존 테스트 | 33 | PASS |
| ContentRelease 신규 테스트 | 14 | PASS |
| **전체** | **47** | **PASS** |

- 테스트 실패: 0건
- 테스트 오류: 0건
- 전체 테스트 실행 시간: 0.128초

실행 명령어:

```powershell
cd backend/django_service
uv run python manage.py test --verbosity 2
```

## 6. 기술적 고려사항

### 데이터 무결성

- DB UNIQUE 제약으로 같은 사건의 버전 중복을 방지합니다.
- Python 검증으로 버전 및 체크섬 문자열 형식을 검사합니다.
- 모델과 QuerySet에서 일반적인 ORM 변경 경로를 제한합니다.

### 남은 한계

1. 실제 manifest와 checksum 간 SHA-256 일치 여부를 검증하지 않습니다.
2. 직접 SQL을 통한 레코드 수정·삭제는 차단하지 않습니다.
3. 게시용 manifest 생성 및 콘텐츠 전체 검증 서비스는 아직 구현되지 않았습니다.
4. DB 동시성 및 모든 우회 저장 경로에 대한 검증은 완료되지 않았습니다.
5. 게시 기록을 이용한 과거 콘텐츠 복원 기능은 구현되지 않았습니다.

### 보안

manifest에 사건 정답, 비공개 증거, 해금 규칙 등이 포함될 수 있으므로 공개 API에서 원문을 반환하지 않아야 합니다.

향후 내부 콘텐츠 API 구현 시 서비스 간 인증과 필드별 접근 권한 정책을 적용해야 합니다.

## 7. 기존 시스템 영향

- FastAPI 게임 엔진 변경 없음
- 플레이어 GameState 변경 없음
- Qdrant 벡터 DB 변경 없음
- Neo4j 관계 그래프 변경 없음
- Django 콘텐츠 DB에 테이블 1개 추가

## 8. 후속 작업

- #106 Django Admin 콘텐츠 관리 기능
- #107 통합 테스트 및 문서화
- 후속 개발: 게시 서비스, 실제 SHA-256 검증, DB 불변성 정책, 인증된 콘텐츠 조회 API

**Issue #105 구현 및 자동화 테스트 완료.**
