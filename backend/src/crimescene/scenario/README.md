# scenario 디렉터리

게임 상태, 증거, 접근 정책 및 판정 규칙.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`access_policy.py`](./access_policy.py) | NPC 정보 접근 검사에 필요한 게임 상태. |
| [`accusation.py`](./accusation.py) | Issue #29 - 범인 지목 및 사건 결과 판정. |
| [`accusation_service.py`](./accusation_service.py) | Issue #29 - 범인 지목 및 SQLite 원자적 저장. |
| [`case_truth.py`](./case_truth.py) | 게임 엔진 전용 사건 진실 원장. |
| [`dataset_validator.py`](./dataset_validator.py) | 사건 데이터 통합 검증 결과. |
| [`document_access.py`](./document_access.py) | 접근 검사를 통과한 플레이어용 문서. |
| [`evidence_acquisition.py`](./evidence_acquisition.py) | CASE-001 증거 획득 정책: 검증된 NPC 카드의 effects.find만 신뢰합니다. |
| [`evidence_collection.py`](./evidence_collection.py) | Issue #28 - 증거 수집 및 점수 관리. |
| [`evidence_service.py`](./evidence_service.py) | Issue #28 - 증거 수집 및 NPC 해금 원자적 처리. |
| [`flag_progress.py`](./flag_progress.py) | Issue #28 - CASE-001 이벤트 기반 플래그 발급. |
| [`game_progress.py`](./game_progress.py) | Issue #27 - 게임 초기화 및 진행 단계 관리. |
| [`integrity.py`](./integrity.py) | 사건 데이터 간 참조 오류. |
| [`json_loader.py`](./json_loader.py) | JSON 파일에서 사건 기본 정보를 불러온다. |
| [`models.py`](./models.py) | 사건 발생 시각의 정확도. |
| [`npc_access.py`](./npc_access.py) | v7.1 NPC 지식 카드의 접근 제어 및 진술 진행 필드. |
| [`npc_knowledge.py`](./npc_knowledge.py) | NPC가 보유한 정보의 유형. |
| [`npc_unlock.py`](./npc_unlock.py) | Issue #28 - NPC 해금 조건 판정 엔진. |
| [`policy_evaluator.py`](./policy_evaluator.py) | CASE-001 접근 정책 판정 엔진. |
| [`rag_access.py`](./rag_access.py) | LLM에 전달할 수 있도록 접근 검사를 마친 정보. |
| [`source_timeline.py`](./source_timeline.py) | v7.1 타임라인의 원본 출처. |
| [`statement_assessment.py`](./statement_assessment.py) | NPC 진술의 객관적 사실 일치 여부. |
| [`statement_integrity.py`](./statement_integrity.py) | NPC 지식, 진술 평가, 사건 타임라인의 참조 무결성을 검사한다. |
| [`timeline_adapter.py`](./timeline_adapter.py) | 타임라인 변환 결과. |

## 하위 폴더

| 폴더 | 설명 |
|---|---|
| [`adapters/`](./adapters/) | adapters 관련 파일 |
| [`loaders/`](./loaders/) | 사건 데이터별 로딩 및 구조 검증 |
| [`schemas/`](./schemas/) | Pydantic 기반 사건 및 게임 상태 데이터 모델 |
| [`validators/`](./validators/) | 인물·문서·관계·타임라인 유효성 검사 |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
