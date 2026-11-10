# trigger 디렉터리

NPC 대화 트리거, 증거 제시 및 원자적 저장.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`atomic_dialogue.py`](./atomic_dialogue.py) | CASE-001: NPC 대화와 GameState를 하나의 SQLite 트랜잭션으로 저장한다. |
| [`case001_dialogue.py`](./case001_dialogue.py) | CASE-001 증거 제시, NPC 트리거, Hybrid RAG의 서버 측 연결 계층. |
| [`dialogue_lock.py`](./dialogue_lock.py) | 동일 프로세스 내 동일 세션 NPC 대화 중복 실행 방지. |
| [`evidence_presentation.py`](./evidence_presentation.py) | Issue #24 - 증거 제시 이벤트 및 NPC 트리거 연동. |
| [`evidence_reaction.py`](./evidence_reaction.py) | Evidence show vs. evidence-trigger distinction for CASE-001. |
| [`npc_trigger.py`](./npc_trigger.py) | Issue #24 - NPC 대화 트리거 엔진. |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
