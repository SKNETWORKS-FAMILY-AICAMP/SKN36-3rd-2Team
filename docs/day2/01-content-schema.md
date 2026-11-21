
# Day 2 — Django 콘텐츠 데이터베이스 스키마 설계

## 1. 설계 개요

- 프로젝트: 마지막 기록: 졸업하지 못한 밤
- GitHub Issue: #102
- 브랜치: feature/102-content-schema
- 기준 문서: Day 1 Django 아키텍처 및 API Contract v3.0
- 데이터베이스: SQLite (개발)
- ORM: Django 5.2

### 설계 목표

1. 게임 콘텐츠 데이터의 체계적 관리
2. 데이터 중복 최소화 및 참조 무결성 확보
3. Django Admin 기반 콘텐츠 관리 지원
4. 향후 PostgreSQL 이전을 고려한 구조
5. FastAPI 게임 상태 데이터와 분리
6. 비공개 사건 정보의 노출 방지

## 2. 데이터베이스 소유권

### Django Content DB

- 사건 메타데이터
- 챕터 콘텐츠
- NPC 콘텐츠
- 증거 정의
- 스토리 이벤트 정의
- 콘텐츠 게시 버전

### FastAPI Game DB

- 게임 세션
- 현재 챕터 및 진행 상태
- NPC 해금 상태
- 증거 획득 상태
- 대화 기록
- 범인 지목 및 엔딩 결과

Django에서는 플레이어별 게임 진행 상태를 저장하지 않는다.

## 3. 공통 설계 원칙

### 기본키

모든 주요 모델은 Django BigAutoField 기반의 내부 PK를 사용한다.

CASE-001, C01, E01 등의 식별자는 비즈니스 식별자로 별도 관리한다.

### 관계

- 1:N 관계: ForeignKey
- 선행 증거 M:N 관계: 자기참조 ManyToManyField
- 복잡한 이벤트 조건: JSONField
- 콘텐츠 메타데이터: JSONField

### 검증

- DB 제약조건: 중복, 참조, 숫자 범위
- Django 모델 검증: 식별자 형식과 비즈니스 규칙
- 서비스 계층 검증: 복합 참조 및 게시 정책

Django의 save()는 기본적으로 full_clean()을 자동 호출하지 않는다.
모델 검증이 필요한 저장 경로에서는 이를 명시적으로 호출한다.

## 4. Case — 사건

테이블: content_case

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| case_id | CharField(20) | UNIQUE, NOT NULL | CASE-001 |
| title | CharField(200) | NOT NULL | 사건 제목 |
| description | TextField | blank 허용 | 공개 사건 소개 |
| status | CharField(20) | choices | 콘텐츠 관리 상태 |

### status

- DRAFT: 작성 중
- REVIEW: 검토 중
- PUBLISHED: 게시 상태
- ARCHIVED: 보관 상태

### 규칙

- case_id는 전역 유일
- 사건 삭제 시 하위 콘텐츠 참조 여부 검사
- 콘텐츠를 참조하는 사건의 무분별한 삭제 방지

## 5. Chapter — 챕터

테이블: content_chapter

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| case | ForeignKey(Case) | NOT NULL | 소속 사건 |
| code | CharField(10) | NOT NULL | CH00~CH04 |
| order | PositiveIntegerField | NOT NULL | 챕터 순서 |
| title | CharField(200) | NOT NULL | 챕터 제목 |
| summary | TextField | blank 허용 | 챕터 요약 |
| metadata | JSONField | default=dict | 추가 콘텐츠 설정 |

### 관계

Case 1 : N Chapter

### 제약조건

- UNIQUE(case, code)
- UNIQUE(case, order)
- order는 0 이상
- code는 CH00~CH04 규칙을 기본 목표로 검증

### 삭제 정책

Chapter.case는 PROTECT를 사용한다.

기존 사건에 연결된 챕터가 있을 경우 사건 삭제를 제한한다.

## 6. Character — NPC

테이블: content_character

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| case | ForeignKey(Case) | NOT NULL | 소속 사건 |
| character_id | CharField(10) | NOT NULL | C01~C10 |
| name | CharField(100) | NOT NULL | NPC 이름 |
| profile | TextField | blank 허용 | 공개용 프로필 |
| metadata | JSONField | default=dict | 관리자 전용 메타데이터 |

### 관계

Case 1 : N Character

### 제약조건

- UNIQUE(case, character_id)
- character_id 형식 검증
- 동일 사건 내 NPC 식별자 중복 금지

### 보안

profile에는 공개 가능한 정보만 저장한다.

진범 정답, 비공개 지식 카드, 관리자 전용 사건 진실은 공개 프로필에 포함하지 않는다.

metadata는 기본적으로 외부 공개 API에서 제외한다.

### 삭제 정책

Character.case는 PROTECT를 사용한다.

## 7. Evidence — 증거

테이블: content_evidence

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| case | ForeignKey(Case) | NOT NULL | 소속 사건 |
| evidence_id | CharField(10) | NOT NULL | E01~E30 |
| name | CharField(200) | NOT NULL | 증거 제목 |
| holder | ForeignKey(Character) | NULL 허용 | 관련 NPC |
| score | PositiveIntegerField | default=0 | 증거 점수 |
| prerequisites | ManyToManyField(self) | blank 허용 | 선행 증거 |
| metadata | JSONField | default=dict | 추가 증거 규칙 |

### 관계

- Case 1 : N Evidence
- Character 1 : N Evidence (holder가 있는 경우)
- Evidence M : N Evidence (선행 증거)

### 제약조건

- UNIQUE(case, evidence_id)
- score는 0 이상
- holder가 존재하면 같은 Case에 소속되어야 함
- 자기 자신을 선행 증거로 참조할 수 없음
- 선행 증거 역시 동일 Case 소속이어야 함
- 순환 선행 관계는 허용하지 않음

### 정규화

prerequisites는 JSON 배열 대신 자기참조 M:N 관계로 설계한다.

Django는 M:N 관계 저장을 위한 중간 테이블을 생성한다.

따라서 주요 도메인 모델은 6개이지만 실제 DB 테이블 수는 더 많을 수 있다.

### 주의사항

ManyToMany 관계는 객체 저장 이후 연결되므로,
선행 증거의 교차 사건 참조·자기 참조·순환 관계는
별도 검증 로직과 테스트가 필요하다.

### 보안

증거 정의와 실제 플레이어의 획득 여부를 분리한다.

미획득 증거의 상세 정보와 해금 조건을 공개 API로 제공하지 않는다.

증거 획득 및 해금 판정은 FastAPI가 담당한다.

### 삭제 정책

Evidence.case 및 Evidence.holder는 PROTECT를 기본 정책으로 한다.

holder는 선택적 관계이지만, 연결된 Character를
삭제하여 증거 참조를 잃는 상황은 방지한다.

선행 증거 삭제 보호는 M:N 관계 구현 시 별도 검증한다.

### 선행 증거 관계 구현 확정

Evidence의 prerequisites는 자기참조 ManyToManyField로 구현한다.

- symmetrical=False
- through="EvidencePrerequisite"
- through_fields=("dependent", "prerequisite")

EvidencePrerequisite는 명시적 연결 모델로 구현한다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BigAutoField | 내부 PK |
| dependent | ForeignKey(Evidence) | 선행 조건을 가진 증거 |
| prerequisite | ForeignKey(Evidence) | 먼저 획득해야 하는 증거 |

제약조건:
- UNIQUE(dependent, prerequisite)
- dependent와 prerequisite는 서로 달라야 함
- 두 증거는 동일한 Case에 속해야 함
- 순환 참조 금지
- 참조된 증거 삭제는 PROTECT

실제 테이블명은 Meta.db_table을 사용해
content_evidence_prerequisite로 지정한다.

동일 사건 확인과 순환 참조 검증은
Django 모델 및 관계 관리 서비스에서 수행한다.

ManyToManyField의 add()는 모델의 save()나
full_clean()을 자동 호출하지 않으므로
관계 생성 경로에서도 검증을 강제한다.

## 8. StoryEvent — 스토리 이벤트

테이블: content_storyevent

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| chapter | ForeignKey(Chapter) | NOT NULL | 연결 챕터 |
| event_key | CharField(100) | UNIQUE | 이벤트 식별자 |
| trigger_type | CharField(50) | NOT NULL | 트리거 유형 |
| conditions | JSONField | default=dict | 이벤트 조건 |
| payload | JSONField | default=dict | 출력 콘텐츠 |

### 관계

Chapter 1 : N StoryEvent

### 트리거 유형 후보

- EVIDENCE_COLLECTED
- NPC_UNLOCKED
- CHAPTER_STARTED
- DIALOGUE_COMPLETED

트리거 유형은 목표 설계안이며,
실제 FastAPI 게임 엔진 지원 범위와 후속 검토한다.

### 제약조건

- event_key는 전역 유일
- 유효한 trigger_type만 허용
- conditions는 정의된 구조의 JSON 객체
- payload는 정의된 구조의 JSON 객체
- 이벤트 조건이 참조하는 ID의 존재 여부 검증

### 처리 책임

Django: 이벤트 정의 및 콘텐츠 관리

FastAPI: 이벤트 발생 조건 평가, 중복 적용 방지,
실제 GameState 변경 및 클라이언트 전달

### 삭제 정책

StoryEvent.chapter는 PROTECT를 사용한다.

## 9. ContentRelease — 콘텐츠 게시 버전

테이블: content_contentrelease

| 컬럼 | Django 타입 | 제약조건 | 설명 |
|---|---|---|---|
| id | BigAutoField | PK | 내부 식별자 |
| case | ForeignKey(Case) | NOT NULL | 대상 사건 |
| version | CharField(30) | NOT NULL | 게시 버전 |
| manifest | JSONField | NOT NULL | 콘텐츠 스냅샷 |
| checksum | CharField(71) | NOT NULL | SHA-256 체크섬 |
| published_at | DateTimeField | NOT NULL | 게시 시각 |

### 관계

Case 1 : N ContentRelease

### 제약조건

- UNIQUE(case, version)
- version은 버전 형식 검증
- checksum 형식: sha256: + 64자리 hexadecimal
- published_at은 게시 시 확정
- 게시 완료된 스냅샷은 수정 불가

### 게시 버전 정책

- 게시된 콘텐츠는 불변
- 콘텐츠 변경 시 신규 version 생성
- 기존 게임 세션은 지정된 version 유지
- 현재 운영 중인 GameState는 Django에서 수정하지 않음

### 구현 범위

이번 Day 2에서는 ContentRelease 모델과
저장 데이터 검증 및 변경 방지 정책을 구현한다.

실제 스냅샷 생성, 체크섬 계산,
게시 서비스 및 내부 API는 후속 이슈에서 구현한다.

### 보안

manifest에는 비공개 콘텐츠가 포함될 수 있다.

공개 API에서는 manifest 원문을 반환하지 않는다.

내부 API는 서비스 간 인증을 적용한 뒤 구현한다.

### 삭제 정책

ContentRelease.case는 PROTECT를 사용한다.

게시 완료된 Release의 수정·삭제는 별도 정책으로 차단한다.

## 10. 인덱스 및 성능

### 인덱스 후보

| 모델 | 대상 | 목적 |
|---|---|---|
| Case | case_id | 사건 단건 조회 |
| Chapter | case, order | 챕터 순서 조회 |
| Character | case, character_id | NPC 조회 |
| Evidence | case, evidence_id | 증거 조회 |
| StoryEvent | chapter, trigger_type | 이벤트 조회 |
| ContentRelease | case, version | 버전 조회 |

UNIQUE 제약조건 및 ForeignKey가 생성하는 인덱스와
중복되는 인덱스는 만들지 않는다.

실제 쿼리 패턴 확인 후 추가 인덱스를 결정한다.

## 11. 데이터 무결성 검증 전략

### DB 레벨

- Primary Key
- Foreign Key
- UniqueConstraint
- CheckConstraint

### Django 모델 레벨

- ID 패턴 검사
- JSON 데이터 구조 검사
- 동일 사건 참조 검증
- 증거 선행 관계 검증

### 서비스 레벨

- 증거 순환 참조 검증
- 스토리 이벤트 조건 검증
- 게시 버전 불변성
- 스냅샷 무결성 검증

### 테스트 레벨

- 정상 데이터 생성
- 중복 데이터 생성 실패
- 잘못된 관계 생성 실패
- 잘못된 JSON 데이터 검증
- 삭제 보호
- 게시 데이터 변경 차단

## 12. 정규화 정책

1. 사건 정보는 Case에 한 번만 저장한다.
2. Chapter, Character, Evidence는 Case를 FK로 참조한다.
3. StoryEvent는 Chapter를 FK로 참조한다.
4. 증거의 선행 관계는 M:N 중간 테이블을 사용한다.
5. JSONField에는 관계형 참조가 아닌 유연한 설정값을 우선 저장한다.
6. 핵심 식별자와 참조를 JSON에 중복 저장하지 않는다.

단, 이벤트 조건의 구조적 참조는
애플리케이션 검증이 필요하다.

## 13. 구현 범위와 제외 범위

### Day 2

- 콘텐츠 모델 6종
- 모델 관계 및 제약조건
- Migration
- Django Admin 관리 기능
- 모델 및 관리자 자동화 테스트

### 후속 Day

- 공개 콘텐츠 API
- 내부 콘텐츠 스냅샷 API
- 콘텐츠 게시 서비스
- FastAPI 콘텐츠 연동
- 실제 챕터 진행 로직
- 증거 E01~E30 동적 처리
- Multi-Agent 및 MCP 연동

## 14. 완료 기준

- [x] 주요 모델 6종 정의
- [x] 모델별 필드 및 데이터 타입 설계
- [x] PK / FK / UNIQUE / CHECK 정책 설계
- [x] Django와 FastAPI 데이터 책임 구분
- [x] 보안 및 비공개 정보 정책 설계
- [x] 정규화 및 인덱스 정책 설계
- [ ] ERD 문서 작성
- [ ] 구현 전 설계 최종 검토

이 문서는 구현 전 설계안이다.
실제 Migration과 검증 결과는 후속 이슈에서 기록한다.
