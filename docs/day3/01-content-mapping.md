# Day 3 — Issue #114: 확장 콘텐츠 데이터 매핑 설계

## 1. 목적

CASE-001 확장 콘텐츠를 기존 Django 콘텐츠 관리 시스템과 FastAPI 게임 엔진에 통합하기 위한 데이터 매핑 및 공개 권한 설계입니다.

- Issue: #114
- Branch: `feature/114-content-mapping`
- 원본: `CASE001_콘텐츠_1120_최종`
- 기준: `content/case001/20_INTEGRATION_GUIDE.md`
- 상태: 설계 초안 (코드 구현 전)

## 2. 기존 Django 모델 매핑

| Django 모델 | 콘텐츠 데이터 | 매핑 |
|---|---|---|
| Case | CASE-001 사건 | 기존 사건 유지 |
| Chapter | CH00~CH04 | `code`, `order`, `title`, `summary` |
| Character | NPC C01~C10 | `character_id`, `name`, `profile`, `metadata` |
| Evidence | E11~E30 | `evidence_id`, `name`, `holder`, `metadata` |
| EvidencePrerequisite | 증거 선행 관계 | ID 기반 관계만 검증 후 매핑 |
| StoryEvent | STORY_011~ | 별도 ID 매핑 필요 |
| ContentRelease | 게시 콘텐츠 버전 | 검증된 콘텐츠 스냅샷 저장 |

기존 E01~E10은 원본 데이터가 완전하지 않으므로 임의로 교체하지 않습니다.

## 3. 확장 데이터 목록

| 파일 | 수량 | 저장 구조 검토 |
|---|---:|---|
| 04_SCENES.json | 30 | Scene 모델 후보 |
| 05_EVIDENCE_E11_E30.csv | 20 | Evidence |
| 07_EVIDENCE_LINKS.csv | 23 | EvidenceLink 모델 후보 |
| 08_NPC_KNOWLEDGE_CARDS.csv | 100 | NPCKnowledgeCard 모델 후보 |
| 08_NPC_SMALLTALK_CARDS.csv | 40 | NPCSmalltalkCard 모델 후보 |
| 09_NPC_DIALOGUE_TRIGGERS.csv | 166 | NPCDialogueTrigger 모델 후보 |
| 10_RELATIONSHIPS.csv | 58 | CharacterRelationship 모델 후보 |
| 12_OBJECTIVES_AND_HINTS.csv | 25 | Objective 모델 후보 |
| 11_ENDINGS.md | 5종 | EndingDefinition 모델 또는 서버 전용 설정 후보 |

추가 모델 후보는 확정된 테이블 목록이 아닙니다. 검색, 수정 빈도, 관계 무결성, 배포 단위를 기준으로 다음 단계에서 결정합니다.

## 4. 증거 데이터 매핑

원본: `05_EVIDENCE_E11_E30.csv`

| 원본 컬럼 | Django 매핑 |
|---|---|
| evidence_id | Evidence.evidence_id |
| title | Evidence.name |
| holder_npc_id | Evidence.holder |
| score_points | 미확정, 직접 적재 금지 |
| finding_public | 공개 조건 적용 후 반환 |
| found_location | 공개 조건 적용 후 반환 |
| category | 메타데이터 후보 |
| chapter | Chapter 참조 후보 |
| scene_id | 장면 참조 후보 |
| prerequisites | 별도 규칙 파싱 및 검증 필요 |
| story_event_id | 이벤트 ID 매핑 필요 |
| truth_dependency | ENGINE_ONLY |
| author_notes | ENGINE_ONLY |
| claim_vs_fact | ENGINE_ONLY |

신규 증거 점수가 모두 미정이므로 백엔드에서 확정하기 전까지 점수 관련 필드는 적재 보류합니다.

## 5. NPC 대화 데이터

### 지식 카드

- 총 100개
- NPC별 소속 관계 유지
- `공개조건` 검증 후 대화 문맥에 포함
- 잠긴 지식은 내용 대신 허용된 회피 태도만 전달
- `모름` 카드는 허용 범위에서 사용

### 잡담 카드

- 총 40개
- 사건 외 질문 처리용
- 답변 범위와 제한을 함께 전달
- 참고 예시는 고정 대사로 취급하지 않음

### 대화 트리거

- 총 166개
- `fixed`: 76개
- `reference`: 90개

`fixed`는 조건 충족 시 고정 문장으로 출력합니다.

`reference`는 말투 참고용이며 고정 출력 대상으로 사용하지 않습니다.

NPC 대화 단계와 증거 제시 이력은 FastAPI 게임 상태를 기준으로 판단합니다.

## 6. 스토리 및 이벤트 구조

### 장면

`04_SCENES.json`에는 30개 장면이 포함되어 있습니다.

주요 필드:

- scene_id
- chapter
- title
- scene_text
- entry_condition_proposal
- player_action
- result_events
- related_evidence
- objective_reference
- visibility

`not_backend_contract=true`가 선언되어 있으므로 원본 JSON을 그대로 API 계약으로 채택하지 않습니다.

### StoryEvent 식별자

현재 Django는 `EVT-CH01-001` 형식을 사용하지만 콘텐츠에는 `STORY_011`과 같은 ID가 사용됩니다.

따라서 원본 이벤트 ID를 보존하면서 내부 StoryEvent와 연결할 매핑 정책이 필요합니다.

### 챕터 진행

CH02와 CH03은 자유 순서 진행을 허용합니다.

챕터 순서가 곧 강제 해금 순서가 되지 않도록 게임 상태와 진입 조건을 분리합니다.

## 7. 엔딩 구조

콘텐츠에서 정의한 엔딩은 다음 5종입니다.

- NO_EVIDENCE
- UNSOLVED
- ESTIMATED
- FULL
- DEEP

특히 DEEP은 FULL 조건 외에 E30 관련 동의·안전 확인과 책임 분리 추론을 요구합니다.

엔딩 조건은 서버 전용으로 보관하고 FastAPI가 판정합니다.

프론트엔드에는 판정된 엔딩의 공개 가능한 출력만 전달합니다.

## 8. 공개 수준 및 보안

| 공개 수준 | 처리 정책 |
|---|---|
| ENGINE_ONLY | 서버 판정 전용. 플레이어 및 NPC AI 접근 금지 |
| NPC_KNOWLEDGE | 해당 NPC의 현재 허용 지식만 전달 |
| UNLOCKED_ONLY | 플레이어 해금 상태 확인 후 반환 |
| PLAYER_VISIBLE | 초기부터 공개 가능한 정보만 반환 |

### 보안 원칙

1. 원본 전체 ZIP을 프론트엔드 정적 파일로 배포하지 않습니다.
2. 전체 NPC 카드와 사건 진상 문서를 RAG 검색 대상에 넣지 않습니다.
3. 콘텐츠 조회 API는 인증·게임 진행 상태를 확인합니다.
4. 게임 상태에 따른 공개 조건은 FastAPI에서 최종 검증합니다.
5. 비공개 필드를 포함한 원본 모델을 직접 직렬화하여 반환하지 않습니다.
6. 관리자 권한과 플레이어 권한을 구분합니다.

## 9. 데이터 Import 정책

- 기존 E01~E10 보존
- ID 기준으로 신규·기존 콘텐츠 식별
- 중복 실행 시 동일 데이터가 중복 생성되지 않도록 설계
- ForeignKey 참조 대상 존재 여부 검증
- 미확정 점수·이미지 경로는 적재 보류 또는 명시적인 미확정 상태 유지
- 유효성 검사를 통과한 콘텐츠만 게시
- 게시 버전은 ContentRelease로 관리
- Import 실패 시 부분 반영 방지를 위한 트랜잭션 적용

## 10. 미확정 및 후속 설계 항목

- 추가 모델의 최종 구성 및 테이블 수
- `STORY_###`와 `EVT-CH##-###`의 매핑 정책
- 증거 점수 및 수집률 분모
- 자연어로 작성된 증거 선행 조건의 구조화 방식
- NPC 카드의 공개 조건 파서
- 엔딩 판정 입력값과 API 계약
- E30 동의·안전 확인 처리
- 기존 데이터와 신규 확장본의 Import 검증 방식

## 11. 결론

기존 Django 모델 7개를 유지하면서 확장 콘텐츠의 저장 구조를 보완합니다.

사건 진상과 콘텐츠 원본은 Django에서 관리하고, 플레이어 상태에 따른 정보 공개 및 게임 판정은 FastAPI에서 수행합니다.

다음 단계에서 추가 모델의 필요성과 API 계약을 확정한 후 구현을 시작합니다.