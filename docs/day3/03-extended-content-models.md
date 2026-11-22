# Day 3 — Issue #117: Django 확장 콘텐츠 모델 구현 보고서

## 1. 작업 개요

CASE-001 확장 스토리 콘텐츠를 관리하기 위해 Django ORM 모델 6종을 추가하고, Migration, Django Admin, 자동화 테스트를 구현했습니다.

- Issue: #117
- Branch: `feature/117-content-models`
- Python: 3.13
- Django: 5.2
- Migration: `0004_extended_content_models`

## 2. 신규 모델 구현

| 모델 | DB 테이블 | 역할 |
|---|---|---|
| Scene | content_scene | 장면 원고 및 공개 수준 관리 |
| NPCCard | content_npc_card | NPC 지식·잡담 카드 관리 |
| NPCDialogueTrigger | content_npc_dialogue_trigger | 고정·참고 대사 및 발동 조건 |
| EvidenceLink | content_evidence_link | 증거 간 추론 관계 |
| CharacterRelationship | content_character_relationship | NPC·증거·외부 인물 간 관계 |
| Objective | content_objective | 목표·힌트·완료 조건 |

기존 Django 모델 7개를 유지하여 콘텐츠 모델 총 13종으로 확장했습니다.

## 3. 모델별 데이터 무결성

### Scene

- 사건별 장면 ID 중복 방지
- `SC-0001` 형식 검증
- 사건과 챕터 소속 일치 검증
- 기본 공개 수준 `UNLOCKED_ONLY`
- 메타데이터 JSON 객체 검증

### NPCCard

- KNOWLEDGE / SMALLTALK 구분
- 카드 ID와 NPC ID 일치 검증
- 카드 유형별 ID 형식 검증
- 공개 조건 및 메타데이터 JSON 객체 검증

### NPCDialogueTrigger

- NPC별 트리거 ID 관리
- 대화 단계 1~3 제한
- fixed / reference 출력 모드 구분
- 기본 비활성화
- 조회용 복합 인덱스 적용

### EvidenceLink

- 동일 사건의 증거만 연결
- 자기참조 차단
- 중복 관계 방지
- 정본 승인 전 활성화 차단
- 증거 선행 조건 모델과 역할 분리

### CharacterRelationship

- NPC / Evidence / Person 대상 유형 지원
- NPC·증거 대상의 동일 사건 소속 검증
- 공개 단계 1~3 검증
- 공개 단계 미확정 시 활성화 차단
- 외부 인물 식별자는 원본 문자열로 관리

### Objective

- 목표 ID 형식 검증
- 힌트 JSON 배열 검증
- 최대 3개 힌트 지원
- 완료 조건 미설정 시 활성화 차단
- 챕터별 목표 ID 중복 방지

## 4. Migration

생성 파일:

`apps/content/migrations/0004_extended_content_models.py`

### 적용 결과

| Migration | 상태 |
|---|---|
| 0001_initial | 적용 |
| 0002_evidence... | 적용 |
| 0003_contentrelease | 적용 |
| 0004_extended_content_models | 적용 |

신규 테이블 6개 생성이 완료되었습니다.

`makemigrations --check --dry-run` 검사에서 추가 스키마 변경이 발견되지 않았습니다.

## 5. Django Admin

기존 모델 7개와 신규 모델 6개를 관리자 페이지에 등록했습니다.

신규 관리자 클래스:

- SceneAdmin
- NPCCardAdmin
- NPCDialogueTriggerAdmin
- EvidenceLinkAdmin
- CharacterRelationshipAdmin
- ObjectiveAdmin

적용 기능:

- 목록 조회 및 검색
- 필터링 및 정렬
- ForeignKey 자동완성
- JSONField 편집
- 활성화 상태 관리
- 모델별 필드 구성

브라우저에서 전체 13개 관리자 메뉴가 표시되는 것을 확인했습니다.

ContentRelease의 조회 전용 정책도 유지되었습니다.

## 6. 자동화 테스트

### 모델 무결성 테스트

신규 13개 테스트를 추가했습니다.

| 모델 | 테스트 |
|---|---:|
| Scene | 2 |
| NPCCard | 2 |
| NPCDialogueTrigger | 2 |
| EvidenceLink | 3 |
| CharacterRelationship | 2 |
| Objective | 2 |
| **합계** | **13** |

### 관리자 테스트

- 신규 관리자 목록 6개 접근 검증
- 신규 관리자 생성 화면 6개 접근 검증
- Scene 정상 생성
- Scene의 사건·챕터 불일치 저장 차단

### 전체 회귀 테스트

| 항목 | 결과 |
|---|---|
| Django 전체 테스트 | 79 PASS |
| FAIL / ERROR | 0 |
| 실행 시간 | 1.635초 |
| 시스템 검사 | PASS |

실행 명령:

```powershell
cd backend/django_service
uv run python manage.py test --verbosity 1
uv run python manage.py makemigrations content --check --dry-run
```

## 7. 보안 및 운영 고려사항

### 현재 구현된 보호 기능

- 기본 비활성화 정책
- 모델 필드 유효성 검사
- 사건 간 잘못된 참조 차단
- 일부 DB CheckConstraint 및 UniqueConstraint
- Django Admin 기본 인증과 모델 권한 체계

### 남은 보완 사항

- 관리자 화면의 활성화 설정은 정본 승인 절차를 대체하지 않음
- `disclosure_policy={}`는 공개 허용을 의미하지 않음
- Django 모델의 `save()` 검증은 `QuerySet.update()` 등 일부 저장 경로에서 우회 가능
- NPC 외부 인물 참조는 DB ForeignKey로 보호되지 않음
- 신규 모델 5종의 관리자 POST 저장 경로는 추가 검증 필요
- 실제 콘텐츠 공개 조건 평가 및 엔딩 판정은 미구현
- 신규 모델을 통한 실제 확장 콘텐츠 Import는 다음 이슈에서 구현

## 8. 변경 파일

- `backend/django_service/apps/content/models.py`
- `backend/django_service/apps/content/admin.py`
- `backend/django_service/apps/content/tests.py`
- `backend/django_service/apps/content/migrations/0004_extended_content_models.py`
- `docs/day3/03-extended-content-models.md`

## 9. 후속 작업

다음 이슈: **#118 — CASE-001 확장 콘텐츠 Import 및 데이터 검증**

주요 작업:

- 원본 JSON·CSV 스키마 검증
- 모델별 데이터 변환
- 참조 무결성 검사
- 기존 E01~E10 보호
- 반복 Import 중복 방지
- 트랜잭션 롤백
- Import 결과 보고서

## 10. 결론

확장 콘텐츠 관리에 필요한 Django 모델 6종과 관리자 기능을 구현했습니다.

Migration 적용 및 Django 자동화 테스트 79개가 통과했습니다.

실제 콘텐츠 Import, 공개 조건 판정 및 FastAPI 연동은 후속 이슈에서 구현합니다.