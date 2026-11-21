# Day 2 — Issue #106: Django Admin 콘텐츠 관리 시스템 구현

## 1. 작업 개요

AI 추리 게임 《마지막 기록: 졸업하지 못한 밤》의 콘텐츠를 관리하기 위해 Django Admin 기반 관리자 기능을 구현했습니다.

기존 Django ORM 모델 7개를 관리자 화면에 등록하고 검색, 필터링, 정렬, 관계형 데이터 조회 및 접근 권한 검증 기능을 추가했습니다.

- Issue: #106
- Branch: `feature/106-content-admin`
- Python: 3.13
- Django: 5.2
- 관리자 주소: `http://127.0.0.1:8001/admin/`

## 2. Django Admin 구현 현황

| 관리자 클래스 | 관리 대상 | 주요 기능 |
|---|---|---|
| CaseAdmin | 사건 | 검색, 상태 필터, CRUD |
| ChapterAdmin | 챕터 | 사건별 필터, 순서 정렬 |
| CharacterAdmin | NPC | 이름 검색, 공개·내부 정보 구분 |
| EvidenceAdmin | 증거 | 사건·NPC 관계, 점수 관리 |
| EvidencePrerequisiteAdmin | 증거 선행 관계 | 후행·선행 증거 조회 및 관리 |
| StoryEventAdmin | 스토리 이벤트 | 트리거, 조건, 출력 콘텐츠 관리 |
| ContentReleaseAdmin | 콘텐츠 게시 버전 | 조회 전용, 변경 차단 |

총 7개 관리자 클래스를 구현했습니다.

## 3. 주요 구현 기능

### 3.1 목록 조회 및 검색

Django ModelAdmin의 다음 기능을 사용했습니다.

- `list_display`: 목록 컬럼 정의
- `search_fields`: 모델 및 관련 모델 검색
- `list_filter`: 사건·상태·트리거별 필터
- `ordering`: 데이터 정렬
- `list_per_page`: 목록 페이지 크기 지정

### 3.2 관계형 데이터 관리

ForeignKey 관계를 관리하기 위해 `autocomplete_fields`를 사용했습니다.

적용 대상:

- Chapter → Case
- Character → Case
- Evidence → Case / Character
- EvidencePrerequisite → Evidence
- StoryEvent → Chapter

`list_select_related`를 사용하여 관련 모델 조회 시 불필요한 추가 쿼리를 줄이도록 구성했습니다.

### 3.3 내부 콘텐츠 관리

`fieldsets`로 편집 화면을 구성했습니다.

- NPC 공개 프로필과 내부 메타데이터 구분
- 증거 기본 정보와 내부 메타데이터 구분
- 이벤트 발동 조건과 출력 콘텐츠 구분

내부 정보 영역에 `collapse`를 적용했습니다.

단, `collapse`는 화면 표시 기능이며 보안 권한을 대체하지 않습니다.

## 4. ContentRelease 읽기 전용 정책

ContentReleaseAdmin은 게시된 콘텐츠 버전을 조회하는 용도로 구성했습니다.

| 작업 | 정책 |
|---|---|
| 목록 조회 | 권한에 따라 허용 |
| 상세 조회 | 권한에 따라 허용 |
| 신규 생성 | 차단 |
| 기존 데이터 수정 | 차단 |
| 기존 데이터 삭제 | 차단 |

사용한 주요 설정:

- `readonly_fields`
- `has_add_permission()`
- `has_change_permission()`
- `has_delete_permission()`

관리자 화면의 권한 제한과 별도로 ContentRelease 모델에서도 주요 ORM 변경 경로를 차단합니다.

다만 직접 SQL 수정·삭제까지 차단하는 DB 수준의 불변성은 구현 범위에 포함되지 않습니다.

## 5. 자동화 테스트 결과

### 신규 Admin HTTP 테스트

| 테스트 항목 | 결과 |
|---|---|
| 관리자 목록 7개 접근 | PASS |
| Case 검색 | PASS |
| 미인증 사용자 접근 제한 | PASS |
| 권한 없는 직원 접근 차단 | PASS |
| ContentRelease 상세 조회 | PASS |
| ContentRelease 신규 생성 차단 | PASS |
| ContentRelease 수정 차단 | PASS |
| ContentRelease 삭제 차단 | PASS |

신규 테스트: **8개 통과**

### 전체 Django 회귀 테스트

| 구분 | 개수 | 결과 |
|---|---:|---|
| 기존 테스트 | 47 | PASS |
| Admin 신규 테스트 | 8 | PASS |
| **전체** | **55** | **PASS** |

- 실패: 0건
- 오류: 0건
- 전체 실행 시간: 1.023초

실행 명령어:

```powershell
cd backend/django_service
uv run python manage.py test --verbosity 2
```

## 6. 실제 브라우저 테스트

Django 개발 서버를 `127.0.0.1:8001`에서 실행하고 관리자 계정으로 로그인했습니다.

### 관리자 메뉴 확인

7개 콘텐츠 관리 메뉴가 모두 정상적으로 표시되는 것을 확인했습니다.

### Case CRUD 검증

테스트용 사건 `CASE-999`를 사용했습니다.

| 단계 | 작업 | 결과 |
|---|---|---|
| CREATE | 테스트 사건 생성 | PASS |
| READ | 사건 목록 조회 | PASS |
| UPDATE | 사건 제목 및 관리 상태 변경 | PASS |
| DELETE | 테스트 사건 삭제 | PASS |

검증 후 임시 데이터 `CASE-999`는 삭제했습니다.

ContentRelease 관리 메뉴에는 조회 전용 접근이 표시되는 것을 확인했습니다.

## 7. 보안 및 데이터 무결성

### 구현된 보호 기능

- Django Admin 사용자 인증
- Django 모델 권한 기반 접근 제어
- 비로그인 사용자 로그인 페이지 이동
- 권한 없는 직원의 관리자 페이지 접근 차단
- ContentRelease 관리 화면 수정·삭제 금지
- 기존 모델의 유효성 검사 및 DB 제약조건 활용

### 향후 보완 사항

- 일반 관리자와 콘텐츠 담당자의 세부 권한 분리
- 내부 메타데이터 접근 권한 정책
- 증거 선행 관계 저장 서비스와 Admin 저장 경로 통합 검토
- 모델별 실제 추가·수정 폼 검증
- 직접 DB 접근에 대한 별도 보안 정책
- 실제 배포 환경의 인증·HTTPS·보안 설정

## 8. 기존 시스템 영향

- 기존 Django 콘텐츠 모델 유지
- Django Admin 설정 및 테스트 코드 추가
- 신규 Migration 불필요
- FastAPI 게임 엔진 변경 없음
- Qdrant 및 Neo4j 변경 없음

## 9. 변경 파일

- `backend/django_service/apps/content/admin.py`
- `backend/django_service/apps/content/tests.py`
- `docs/day2/06-content-admin.md`

## 10. 후속 작업

**Issue #106 구현 및 검증 완료**

다음 작업은 Issue #107 통합 테스트 및 문서화입니다.

주요 검증 대상으로 관리자 편집 폼, 모델 간 참조 무결성, Migration 재현성, 데이터 접근 권한, FastAPI 회귀 테스트를 포함합니다.