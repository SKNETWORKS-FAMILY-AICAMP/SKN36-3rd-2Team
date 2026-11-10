# chat 디렉터리

LLM 호출, NPC 대화, 페르소나 및 대화 기록.

## 파일 구성

| 파일 | 역할 |
|---|---|
| [`__init__.py`](./__init__.py) | Python 패키지 초기화 파일 |
| [`llm_client.py`](./llm_client.py) | NPC LLM 공급자 선택: Ollama(개발용) 또는 OpenAI(서비스용). |
| [`npc_behavior.py`](./npc_behavior.py) | CASE-001 NPC의 GameState 기반 행동 및 대화 규칙 구성. |
| [`npc_chat_runtime.py`](./npc_chat_runtime.py) | Issue #23 - NPC RAG, Ollama, 출력 검증 및 세션 저장 통합. |
| [`npc_history_context.py`](./npc_history_context.py) | Issue #23 - 접근 권한을 유지하는 NPC 대화 컨텍스트. |
| [`npc_history_display.py`](./npc_history_display.py) | 저장된 NPC 대화를 출처 노출 없이 화면용 대사로 변환합니다. |
| [`npc_natural_reply.py`](./npc_natural_reply.py) | Issue #25 - 검증된 NPC 진술의 안전한 화면 출력. |
| [`npc_persona.py`](./npc_persona.py) | CASE-001 NPC의 비밀 정보를 제외한 페르소나와 시스템 프롬프트. |
| [`npc_rag_service.py`](./npc_rag_service.py) | Issue #23 - NPC 세션과 접근 제어 Hybrid RAG 검색 연결. |
| [`npc_reaction.py`](./npc_reaction.py) | Issue #25 - NPC별 감정 및 대화 반응 판단. |
| [`npc_session.py`](./npc_session.py) | Issue #23 - NPC별 대화 세션 및 영구 저장소 연동. |
| [`npc_session_repository.py`](./npc_session_repository.py) | Issue #23 - SQLite 기반 NPC 대화 기록 영구 저장소. |
| [`npc_social_dialogue.py`](./npc_social_dialogue.py) | Issue #25 - NPC별 안전한 일상 대화. |
| [`npc_social_style.py`](./npc_social_style.py) | CASE-001 NPC의 기본 말투와 조건부 행동을 분리한다. |

## 관련 문서

- [프로젝트 전체 README](../../../../README.md)
