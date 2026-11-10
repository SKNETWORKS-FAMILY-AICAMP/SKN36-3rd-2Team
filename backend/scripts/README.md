# scripts 디렉터리

RAG 검색 평가, NPC 검증 및 데이터 점검 스크립트.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`audit_case001_trigger_security.py`](./audit_case001_trigger_security.py) | Issue #24 - CASE-001 실제 데이터 기반 NPC 접근 보안 검증. |
| [`build_retrieval_eval_provisional.py`](./build_retrieval_eval_provisional.py) | CASE-001 임시 검색 평가 데이터셋 생성. |
| [`create_retrieval_eval_draft.py`](./create_retrieval_eval_draft.py) | 로컬 Ollama를 이용한 CASE-001 검색 평가 질문 초안 생성. |
| [`evaluate_issue24_e2e.py`](./evaluate_issue24_e2e.py) | Issue #24: CASE-001 NPC 증거 제시 전후 실제 Hybrid RAG 및 SQLite E2E. |
| [`evaluate_npc_persona.py`](./evaluate_npc_persona.py) | Issue #22 - 실제 Ollama NPC 페르소나 응답 비교. |
| [`evaluate_npc_rag_e2e.py`](./evaluate_npc_rag_e2e.py) | Issue #23 - 실제 CASE-001 NPC RAG 대화 E2E 검증. |
| [`review_retrieval_eval_draft.py`](./review_retrieval_eval_draft.py) | CASE-001 검색 평가 질문 검수 보고서 생성. |
| [`revise_retrieval_eval_draft.py`](./revise_retrieval_eval_draft.py) | CASE-001 검색 평가 질문을 실제 플레이어 대화체로 수정한다. |
| [`run_retrieval_eval.py`](./run_retrieval_eval.py) | CASE-001 실제 Qdrant 검색 성능 비교. |

## 관련 문서

- [프로젝트 전체 README](../../README.md)
