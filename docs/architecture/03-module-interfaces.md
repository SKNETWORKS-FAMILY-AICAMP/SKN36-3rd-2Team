# CASE-001 — 모듈 구조 및 인터페이스

## 1. 문서 개요

본 문서는 AI 크라임씬 《마지막 기록: 사라진 공동체》의 주요 소프트웨어 모듈, 파일별 역할 및 모듈 간 인터페이스를 설명합니다.

프로젝트는 React 프론트엔드와 FastAPI 백엔드를 중심으로 구성되며, LLM + Hybrid RAG 기반 NPC 대화와 Python 기반 게임 진행 엔진을 결합합니다.

### 설계 원칙

- 프론트엔드는 게임 상태를 표시하고 사용자 입력을 전달합니다.
- 게임 상태, 증거 획득, 인물 해금 및 범인 판정은 백엔드에서 처리합니다.
- NPC 응답은 LLM이 생성하지만, 참조할 수 있는 사건 정보는 접근 정책에 따라 제한합니다.
- 게임 진행 상태는 SQLite에 저장합니다.
- 비공개 사건 정답은 일반적인 RAG 검색 대상에 포함하지 않습니다.

## 2. 전체 모듈 구성

| 모듈 | 주요 경로 | 역할 |
|---|---|---|
| Frontend | `frontend/src/` | 게임 화면 및 사용자 인터페이스 |
| API | `backend/src/crimescene/api/` | FastAPI 엔드포인트 및 요청 처리 |
| Chat | `backend/src/crimescene/chat/` | NPC 대화, 페르소나 및 LLM 연동 |
| Retriever | `backend/src/crimescene/retriever/` | Hybrid RAG 검색 및 접근 권한 검증 |
| Scenario | `backend/src/crimescene/scenario/` | 게임 규칙, 증거, 인물 해금 및 범인 지목 |
| Trigger | `backend/src/crimescene/trigger/` | 대화 이벤트, 증거 제시 및 상태 변경 |
| Ingest | `backend/src/crimescene/ingest/` | 문서 로딩, 청킹 및 임베딩 |
| Database | `backend/src/crimescene/db/` | Qdrant·Neo4j 연결 및 데이터 관리 |

## 3. Frontend 인터페이스

**주요 경로:** `frontend/src/`

React 18, TypeScript 및 Vite를 이용하여 플레이어가 게임을 진행하는 화면을 제공합니다.

### 주요 파일

| 파일 | 역할 |
|---|---|
| `App.tsx` | 전체 게임 화면 구성 |
| `main.tsx` | React 애플리케이션 진입점 |
| `config.ts` | 프론트엔드 실행 설정 |
| `api/client.ts` | API 클라이언트 구성 |
| `api/httpApi.ts` | FastAPI HTTP 요청 처리 |
| `api/mockApi.ts` | 개발용 Mock API |
| `api/types.ts` | API 데이터 타입 정의 |
| `store/gameStore.ts` | 게임 진행 상태 관리 |
| `store/chatStore.ts` | NPC 대화 상태 관리 |
| `store/noteStore.ts` | 플레이어 메모 상태 관리 |

### 주요 게임 화면

| 화면 | 파일 | 역할 |
|---|---|---|
| 메인 | `screens/Main/Main.tsx` | 게임 시작 및 진입 |
| 스토리 | `screens/Story/Story.tsx` | 프롤로그 및 사건 스토리 |
| 대화 | `screens/Chat/Chat.tsx` | NPC와 자유로운 대화 |
| 증거 | `screens/Evidence/Evidence.tsx` | 수집한 증거 확인 |
| 관계도 | `screens/Relations/Relations.tsx` | 인물 관계 탐색 |
| 수첩 | `screens/Notes/Notes.tsx` | 플레이어 조사 기록 |
| 지목 | `screens/Accuse/Accuse.tsx` | 범인 지목 |
| 엔딩 | `screens/Final/Final.tsx` | 게임 결과 표시 |

프론트엔드는 백엔드에서 전달받은 게임 상태를 사용하며, 증거 점수와 정답 판정을 클라이언트에서 직접 수행하지 않습니다.

## 4. FastAPI 인터페이스

**주요 경로:** `backend/src/crimescene/api/`

게임 생성, 상태 조회, NPC 대화, 증거 수집 및 범인 지목 요청을 처리합니다.

### 주요 파일

| 파일 | 역할 |
|---|---|
| `app.py` | API 라우트 및 요청·응답 처리 |
| `main.py` | FastAPI 애플리케이션 초기화 |
| `chat_bootstrap.py` | NPC 대화 및 RAG 실행 리소스 초기화 |

### 주요 API

| 메서드 | 경로 | 기능 |
|---|---|---|
| POST | `/api/games` | 새 게임 생성 |
| GET | `/api/games/{session_id}` | 게임 상태 조회 |
| POST | `/api/games/{session_id}/prologue/complete` | 프롤로그 완료 |
| POST | `/api/games/{session_id}/characters/{npc_id}/select` | NPC 선택 |
| POST | `/api/games/{session_id}/chat` | NPC 대화 및 증거 제시 |
| GET | `/api/games/{session_id}/evidence/available` | 수집 가능한 증거 확인 |
| POST | `/api/games/{session_id}/evidence/{evidence_id}/collect` | 증거 수집 |
| POST | `/api/games/{session_id}/accusations` | 범인 지목 |
| GET | `/api/games/{session_id}/ending` | 게임 엔딩 조회 |

### API 주요 응답 데이터

| 필드 | 설명 |
|---|---|
| `sessionId` | 게임 세션 식별자 |
| `phase` | 현재 게임 진행 단계 |
| `activeCharacterId` | 현재 선택된 NPC |
| `unlockedCharacters` | 해금된 NPC 목록 |
| `collection` | 증거 점수 및 총점 |
| `canAccuse` | 범인 지목 가능 여부 |
| `attemptsLeft` | 남은 지목 기회 |
| `outcome` | 게임 결과 |
| `revision` | 게임 상태 변경 버전 |
| `events` | UI 갱신용 게임 이벤트 |

## 5. NPC 대화 모듈

**주요 경로:** `backend/src/crimescene/chat/`

NPC별 페르소나, 대화 기록 및 LLM 응답 생성을 관리합니다.

| 파일 | 역할 |
|---|---|
| `llm_client.py` | Ollama 및 지원되는 LLM 공급자 호출 |
| `npc_persona.py` | NPC별 성격과 말투 관리 |
| `npc_chat_runtime.py` | NPC 대화 실행 및 응답 생성 |
| `npc_rag_service.py` | NPC 대화에 Hybrid RAG 연결 |
| `npc_behavior.py` | NPC별 행동 및 반응 규칙 |
| `npc_reaction.py` | 상황별 NPC 반응 |
| `npc_natural_reply.py` | 플레이어 화면용 자연스러운 응답 구성 |
| `npc_history_context.py` | 이전 대화를 참고한 문맥 구성 |
| `npc_history_display.py` | 대화 기록 표시 처리 |
| `npc_session.py` | NPC 대화 세션 관리 |
| `npc_session_repository.py` | 대화 기록 저장 및 조회 |
| `npc_social_dialogue.py` | 일상 대화 처리 |
| `npc_social_style.py` | NPC별 일상 대화 표현 관리 |

### 처리 방식

1. 현재 선택된 NPC와 플레이어 질문을 확인합니다.
2. 질문이 일상 대화인지 사건 관련 질문인지 처리합니다.
3. 사건 관련 질문은 NPC별 접근 정책을 확인합니다.
4. 허용된 사건 정보에 대해 RAG 검색을 수행합니다.
5. 검색된 근거와 NPC 페르소나를 이용해 LLM 응답을 생성합니다.
6. 응답의 근거 및 공개 가능 여부를 검증합니다.
7. 대화 기록과 필요한 게임 상태를 저장합니다.

## 6. Hybrid RAG 검색 모듈

**주요 경로:** `backend/src/crimescene/retriever/`

### 검색 기능

| 파일 | 역할 |
|---|---|
| `dense_search.py` | 임베딩 기반 의미 검색 |
| `sparse_search.py` | 키워드 기반 검색 |
| `korean_bm25.py` | 한국어 형태소 분석 기반 BM25 |
| `graph_retriever.py` | Neo4j 그래프 검색 |
| `hybrid_search.py` | Dense와 Sparse 검색 통합 |
| `multisource_search.py` | 여러 검색 소스 통합 |
| `rrf_fusion.py` | 검색 결과 순위 통합 |
| `multisource_rrf.py` | 다중 소스 RRF 적용 |
| `query_entity_extractor.py` | 질문의 주요 엔티티 추출 |

### 접근 제어 및 응답 검증

| 파일 | 역할 |
|---|---|
| `authorized_hybrid_search.py` | 접근 정책을 적용한 검색 |
| `authorized_multisource_context.py` | 권한이 검증된 다중 소스 컨텍스트 구성 |
| `npc_presearch_access.py` | 검색 이전 권한 검증 |
| `npc_graph_knowledge_guard.py` | NPC 그래프 지식 공개 제한 |
| `npc_output_guard.py` | NPC 응답 근거 검증 |
| `npc_response_gate.py` | 허용되지 않는 응답 차단 |

### 검색 과정

- Dense Search: 의미적으로 유사한 사건 정보 검색
- BM25: 인물명, 장소명, 사건 관련 키워드 검색
- Graph Retrieval: 인물·사건·증거의 관계 정보 검색
- RRF: 다중 검색 결과의 순위 통합
- Access Control: 게임 상태 및 NPC에 따라 공개 가능한 정보 제한

## 7. 게임 규칙 및 상태 관리 모듈

**주요 경로:** `backend/src/crimescene/scenario/`

| 파일 | 역할 |
|---|---|
| `game_progress.py` | 게임 초기 상태 및 단계 전환 |
| `evidence_collection.py` | 증거 수집 및 점수 계산 |
| `evidence_service.py` | 증거 수집과 NPC 해금의 통합 처리 |
| `evidence_acquisition.py` | 증거 획득 조건 및 정책 구성 |
| `npc_unlock.py` | NPC 해금 조건 판단 |
| `policy_evaluator.py` | 정보 접근 정책 평가 |
| `flag_progress.py` | 게임 진행 플래그 관리 |
| `accusation.py` | 범인 지목 가능 조건 및 판정 |
| `accusation_service.py` | 범인 지목 결과 영구 저장 |
| `case_truth.py` | 사건 정답 데이터 모델 |
| `rag_access.py` | RAG 정보 접근 제어 |

### GameState

게임 상태는 `scenario/schemas/game_state.py`에서 정의합니다.

주요 상태는 다음과 같습니다.

- `session_id`: 게임 세션
- `phase`: 현재 진행 단계
- `unlocked_characters`: 해금된 NPC
- `evidence`: 수집한 증거
- `flags`: 진행 플래그
- `presented`: 증거 제시 기록
- `attempts_left`: 남은 지목 기회
- `score`: 증거 점수
- `outcome`: 최종 결과
- `revision`: 상태 변경 버전

### 게임 진행 규칙

| 항목 | 규칙 |
|---|---|
| 등장인물 | 10명 |
| 증거 | 10개 |
| 증거 총점 | 21점 |
| 범인 지목 조건 | 증거 5개 이상 및 11점 이상 |
| 지목 기회 | 최대 3회 |
| 게임 종료 | 정답 지목 또는 지목 기회 소진 |

## 8. Trigger 모듈

**주요 경로:** `backend/src/crimescene/trigger/`

| 파일 | 역할 |
|---|---|
| `case001_dialogue.py` | NPC 대화와 사건 진행 연결 |
| `atomic_dialogue.py` | SQLite 트랜잭션 기반 대화 및 상태 저장 |
| `dialogue_lock.py` | 동일 세션 동시 요청 제한 |
| `evidence_presentation.py` | NPC 증거 제시 처리 |
| `evidence_reaction.py` | 증거 제시에 대한 NPC 반응 |
| `npc_trigger.py` | 특정 질문 및 조건에 따른 정보 공개 |

게임 진행에 영향을 주는 대화 결과는 서버의 규칙과 접근 정책을 거쳐 처리합니다.

## 9. 데이터 적재 및 데이터베이스 모듈

### Ingest

**경로:** `backend/src/crimescene/ingest/`

사건 문서와 NPC 지식 카드를 로딩하고 검색 가능한 청크와 임베딩으로 변환합니다.

주요 기능은 다음과 같습니다.

- 원본 문서 로딩
- 의미 기반 및 고정 길이 청킹
- NPC 지식 카드 분할
- 플레이어 문서 분할
- Ollama 임베딩 생성
- 문서별 메타데이터 및 접근 정보 구성

### Database

**경로:** `backend/src/crimescene/db/`

| 저장소 | 역할 |
|---|---|
| Qdrant | Dense 임베딩 및 문서 검색 |
| BM25 | 한국어 키워드 검색 인덱스 |
| Neo4j | 인물·사건·증거 관계 및 이벤트 |
| SQLite | 게임 진행 상태 및 NPC 대화 기록 |

Qdrant·Neo4j 데이터 적재 및 동기화는 `db/` 모듈에서 관리합니다.

SQLite의 플레이어 세션과 대화 기록은 게임 진행 모듈 및 대화 저장소에서 처리합니다.

## 10. 모듈 간 주요 호출 관계

| 호출 주체 | 대상 모듈 | 주요 동작 |
|---|---|---|
| React | FastAPI | 게임 API 요청 |
| FastAPI | Scenario | 게임 상태 조회 및 규칙 적용 |
| FastAPI | Trigger | NPC 대화 및 증거 제시 |
| Trigger | Chat | NPC 응답 생성 |
| Chat | Retriever | NPC 지식 검색 |
| Retriever | Qdrant·Neo4j | 검색 및 관계 정보 조회 |
| Chat | LLM | 승인된 근거를 이용한 답변 생성 |
| Scenario | SQLite | 상태 변경 저장 |
| Trigger | SQLite | 대화 및 게임 상태 저장 |
| FastAPI | React | 검증된 응답과 이벤트 반환 |

## 11. 보안 및 무결성

### 정보 접근 제어

- NPC가 알 수 없는 비공개 정보는 검색 전에 차단합니다.
- 검색된 문서는 LLM 전달 전에 접근 권한을 다시 검증합니다.
- 비공개 사건 정답은 일반 대화용 검색 정보와 분리합니다.
- 승인된 근거가 없는 사건 진술은 응답 검증 단계에서 제한합니다.

### 게임 상태 무결성

- 점수, 증거 수집 및 NPC 해금은 서버에서 판정합니다.
- 상태 변경 시 `revision`을 검증합니다.
- 대화 기록과 게임 상태 변경은 원자적으로 저장합니다.
- 중복 요청 및 종료된 게임에 대한 잘못된 진행 요청을 차단합니다.

## 12. 관련 문서

- [시스템 개요](./01-system-overview.md)
- [시스템 처리 흐름](./02-system-flow.md)
- [데이터 저장 구조](./04-data-storage.md)
- [프로젝트 README](../../README.md)