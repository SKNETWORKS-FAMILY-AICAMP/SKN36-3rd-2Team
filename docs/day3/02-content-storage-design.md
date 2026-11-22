# Day 3 — Issue #114: Django 확장 콘텐츠 저장 구조 설계

## 1. 설계 목표

CASE-001 확장 콘텐츠를 Django ORM에 통합하되 기존 콘텐츠 모델과 게임 엔진의 호환성을 유지합니다.

- 기존 모델 7개 유지
- 신규 모델 6개 추가 제안
- 기존 StoryEvent 식별자 매핑 보완
- 공개 조건은 서버에서 검증
- 미확정 콘텐츠는 게시되지 않도록 관리

## 2. 신규 모델

### 2.1 Scene

스토리 장면 30개를 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| chapter | ForeignKey(Chapter) | 소속 챕터 |
| scene_id | CharField | SC-0001 형식 |
| title | CharField | 장면 제목 |
| scene_text | TextField | 장면 원고 |
| visibility | CharField | 공개 수준 |
| metadata | JSONField | 연출, 퍼즐, 목표, 이벤트 정보 |

제약조건:
- 사건별 장면 ID 유일성
- 챕터 연결 필수
- 미해금 장면의 원고 공개 금지

원본의 `not_backend_contract=true`를 존중하여 제안 필드를 확정된 게임 API로 취급하지 않습니다.

### 2.2 NPCCard

NPC 지식 카드 100개와 잡담 카드 40개를 통합 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| character | ForeignKey(Character) | 카드 소유 NPC |
| card_id | CharField | 원본 카드 ID |
| card_type | CharField | KNOWLEDGE / SMALLTALK |
| content | TextField | 카드의 핵심 정보 |
| disclosure_policy | JSONField | 구조화된 공개 조건 |
| metadata | JSONField | 지식 상태, 답변 범위, 말투 등 |

제약조건:
- 사건·NPC별 카드 ID 충돌 검사
- NPC 간 지식 공유 금지
- 공개 조건을 통과한 카드만 대화 문맥에 포함
- 복잡한 자연어 조건은 검증 전 비공개

SMALLTALK는 해당 NPC의 일반 대화 문맥에 사용할 수 있지만, 다른 NPC에게 전달하지 않습니다.

### 2.3 NPCDialogueTrigger

NPC 대사 트리거 166개를 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| character | ForeignKey(Character) | 대상 NPC |
| stage | PositiveSmallIntegerField | 대화 단계 1~3 |
| trigger_type | CharField | question / evidence / evidence_combo / verbal_only |
| output_mode | CharField | fixed / reference |
| response_text | TextField | 대사 원문 |
| condition_key | CharField | 발동 조건 식별자 |
| output_order | PositiveIntegerField | 출력 순서 |
| metadata | JSONField | 증거 조합, 반복 조건, 단계 변화 등 |

고정 대사 76개와 참고 대사 90개를 구분합니다.

- fixed: 조건 충족 시 원문 출력
- reference: 허용된 말투 예시로만 사용
- NPC 단계 변경: FastAPI 게임 상태에서 처리
- 조건 미충족 또는 미지원 condition_key: 출력 금지

원본에는 고유한 행 ID가 없으므로 Import 과정에서 안정적인 식별자를 부여하는 정책이 필요합니다.

### 2.4 EvidenceLink

증거 간 추론 관계 23개를 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| from_evidence | ForeignKey(Evidence) | 시작 증거 |
| to_evidence | ForeignKey(Evidence) | 대상 증거 |
| relationship | CharField | 관계 유형 |
| resulting_inference | CharField | 도출되는 추론 ID |
| needs_canon_approval | BooleanField | 정본 승인 필요 여부 |
| metadata | JSONField | 출력 방식, 이벤트, 메모 |

제약조건:
- 같은 사건의 증거만 연결
- 동일한 관계 중복 방지
- 정본 미승인 관계는 추론·해금 엔진에 적용 금지
- 기존 EvidencePrerequisite와 역할 분리

### 2.5 CharacterRelationship

NPC를 출발점으로 하는 관계 58개를 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| source_character | ForeignKey(Character) | 출발 NPC |
| target_type | CharField | npc / evidence / person |
| target_id | CharField | 관계 대상 식별자 |
| relationship | TextField | 관계 설명 |
| public_from_stage | PositiveSmallIntegerField | 최소 공개 단계 |
| metadata | JSONField | 출처, 기간 등 |

대상 유형이 혼합되어 있으므로 단일 NPC ForeignKey를 사용하지 않습니다.

- npc: Character 존재 여부 검증
- evidence: Evidence 존재 여부 검증
- person: 원본 식별자 보존, 별도 인물 정의 여부 확인
- 공개 단계 도달 전 관계 설명 비공개

다형적 참조의 무결성은 Django 서비스 계층에서 별도로 검증합니다.

### 2.6 Objective

플레이어 목표와 힌트 25개를 관리합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| chapter | ForeignKey(Chapter) | 소속 챕터 |
| objective_id | CharField | 목표 식별자 |
| player_goal | TextField | 목표 설명 |
| hints | JSONField | 단계별 힌트 |
| completion_rule | JSONField | 완료 조건 |
| metadata | JSONField | 관련 증거, 출처, 상태 |

원본 목표 25건의 완료 조건이 모두 미정이므로 검증 전에는 자동 완료 판정에 사용하지 않습니다.

## 3. 기존 모델 변경 제안

### StoryEvent

원본 `STORY_011` 형식과 Django `EVT-CH01-001` 형식을 구분합니다.

추가 제안:

- `source_event_id`: nullable, unique CharField
- 기존 `event_key` 규칙 유지
- Import 시 원본 ID와 Django 내부 이벤트 ID를 연결

기존 이벤트 ID를 일괄 변경하지 않습니다.

### Evidence

E11~E30 데이터는 기존 모델에 연결합니다.

단, `score_points`가 미정인 상태에서 기존 기본값 0을 확정된 게임 점수처럼 사용하는 것을 금지합니다.

점수 정책이 정해지기 전까지 실제 증거 적재 및 게시를 보류하거나, 미확정 상태를 표현할 명시적인 모델 변경을 별도 승인받습니다.

### ContentRelease

검증을 완료한 콘텐츠만 버전별 스냅샷으로 관리합니다.

- 원본 데이터와 게시 버전 구분
- 게임 실행 중 참조하는 콘텐츠 버전 고정
- 게시 스냅샷 변경 금지
- 서버 전용 데이터의 외부 직렬화 금지

## 4. 별도 모델을 추가하지 않는 데이터

| 데이터 | 저장 방안 |
|---|---|
| 사건 진상 원장 | 서버 전용 콘텐츠 자산 |
| 마스터 타임라인 | 서버 전용 콘텐츠 자산 |
| 엔딩 5종 원고·판정 조건 | 서버 전용 정의 및 게시 스냅샷 |
| 장면 퍼즐 초안 | Scene.metadata |
| NPC 잡담 상세 설정 | NPCCard.metadata |
| 증거 문서의 내부 작성 메모 | 서버 전용 콘텐츠 |
| 이미지 요청 목록 | 프론트엔드 자산 관리 대상 |

엔딩 판정은 FastAPI가 수행합니다. 원고와 판정 조건을 플레이어에게 미리 전달하지 않습니다.

## 5. 공개 정책

| 공개 수준 | 접근 가능 범위 |
|---|---|
| ENGINE_ONLY | 서버 내부 판정 기능 |
| NPC_KNOWLEDGE | 대상 NPC의 허용된 대화 문맥 |
| UNLOCKED_ONLY | 플레이어 진행 상태 검증 후 |
| PLAYER_VISIBLE | 공개 API에서 허용한 필드 |

### 필수 규칙

- Django API는 공개 가능한 필드만 직렬화합니다.
- FastAPI는 플레이어별 해금 상태를 최종 검증합니다.
- 비공개 데이터를 프론트엔드에 전달한 뒤 숨기는 방식은 금지합니다.
- 전체 사건 진상을 NPC RAG 검색 인덱스에 포함하지 않습니다.
- 알 수 없는 공개 조건은 기본적으로 거부합니다.

## 6. Import 설계 원칙

1. 원본 ID를 보존합니다.
2. E01~E10 기존 정보를 덮어쓰지 않습니다.
3. 원본 SHA-256과 Import 결과를 기록합니다.
4. 같은 버전의 반복 Import에서 데이터가 중복되지 않도록 합니다.
5. 참조 누락 및 사건 간 연결을 검증합니다.
6. 승인되지 않은 콘텐츠를 활성화하지 않습니다.
7. 실패 시 트랜잭션을 롤백합니다.
8. Import와 게시 작업을 별도 단계로 관리합니다.

## 7. 미확정 항목

- Evidence 점수 및 수집률 계산 정책
- 복잡한 NPC 공개 조건의 구조화 방식
- 증거 관계 23건의 정본 승인
- 목표 25건의 완료 조건
- 엔딩 판정 입력 스키마
- 기존 E01~E10과 신규 콘텐츠 연결
- E30 동의·안전 확인 절차
- Django–FastAPI 콘텐츠 조회 계약

## 8. 다음 단계

설계 검토가 완료되면 신규 모델 구현 및 Migration을 별도 GitHub Issue에서 진행합니다.

Issue #114에서는 기존 모델과의 매핑, 저장 구조, 공개 정책을 우선 확정합니다.