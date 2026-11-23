# Day 4 — Multi-Agent 아키텍처 및 실행 계약

## 1. 개요

| 항목 | 내용 |
|---|---|
| 프로젝트 | 마지막 기록: 졸업하지 못한 밤 |
| 개발 단계 | 4차 단위 프로젝트 Day 4 |
| 관련 이슈 | #129 |
| 기준 브랜치 | `dev` |
| 작업 브랜치 | `feature/129-agent-contracts` |
| Python | 3.13.15 |
| Pydantic | 2.14.2 |
| 개발 마감 | 2026-12-02 |

### 개발 목적

기존 AI 추리 게임에 Multi-Agent 실행 구조를 도입하기 위해 Agent별 책임과 공통 인터페이스를 정의합니다.

기존 FastAPI, Django, Hybrid RAG 및 게임 상태 관리 코드를 유지하면서 신규 Agent를 단계적으로 연결합니다.

## 2. 기존 아키텍처 분석

### 2.1 기존 주요 구성 요소

| 구성 요소 | 기존 구현 | 역할 |
|---|---|---|
| FastAPI | `api/app.py` | 게임 API, 세션 소유권 검증 |
| Chat Runtime | `chat/npc_chat_runtime.py` | NPC 대화 실행 및 검증 |
| NPC RAG | `chat/npc_rag_service.py` | NPC별 Hybrid RAG |
| Authorized Search | `retriever/authorized_hybrid_search.py` | 검색 결과 접근 제한 |
| Atomic Dialogue | `trigger/atomic_dialogue.py` | 대화 및 게임 상태 원자적 저장 |
| GameState | `scenario/schemas/game_state.py` | 게임 진행 상태 |
| Django Client | `api/django_content_client.py` | 콘텐츠 승인 API 연동 |

### 2.2 유지할 설계 원칙

1. FastAPI는 플레이어 세션과 GameState를 관리합니다.
2. Django는 콘텐츠 정의 및 승인 정책을 관리합니다.
3. NPC Agent는 기존 대화 엔진을 Adapter 방식으로 재사용합니다.
4. Hybrid RAG 검색 및 출력 검증을 재구현하지 않습니다.
5. 신규 Agent는 기본적으로 읽기 전용입니다.
6. GameState 변경은 기존 승인된 게임 엔진 경로를 통해 수행합니다.

## 3. Multi-Agent 아키텍처

```text
React Frontend
      |
      v
FastAPI Game API
      |
      v
Session Ownership Validation
      |
      v
Agent Orchestrator
      |
      +-- NPC Agent
      |      |
      |      +-- Existing NPC Chat Engine
      |      +-- Hybrid RAG
      |
      +-- Deduction Agent
      |      |
      |      +-- Authorized Evidence
      |      +-- Graph Relations
      |
      +-- Hint Agent
             |
             +-- Investigation Progress
             +-- Authorized Evidence
      |
      v
Response Authorization / Output Guard
      |
      v
Player Response

Shared Services:
- FastAPI GameState / SQLite
- Django Content Client
- Qdrant / Neo4j
- Read-only MCP Tools (planned)
```

위 구조는 목표 아키텍처이며 Issue #129에서는 실행 계약을 우선 정의합니다.

실제 Orchestrator, Agent Adapter, MCP Server 구현은 후속 하위 이슈에서 진행합니다.

## 4. Agent 역할 및 책임

### 4.1 NPC Agent

**목적:** 플레이어와 NPC 사이의 대화를 처리합니다.

담당 기능:
- NPC 페르소나와 말투 유지
- 기존 Hybrid RAG 기반 지식 검색
- NPC별 지식 공개 제한
- 챕터 및 증거 진행 상태 검증
- 검증된 대화 결과 저장

구현 방식:
- 기존 `run_case001_npc_dialogue_atomic()` 재사용
- 기존 NPC 출력 검증 유지
- 기존 SQLite 원자적 커밋 경로 사용

NPC Agent Adapter에서 별도의 대화 저장 로직을 구현하지 않습니다.

### 4.2 Deduction Agent

**목적:** 플레이어가 확보한 증거를 바탕으로 추론을 지원합니다.

담당 기능:
- 확보한 증거 분석
- 증거 관계 확인
- 추리 주장과 근거의 일치 여부 검토
- 근거 부족 및 모순 여부 검토

제한사항:
- 미획득 증거 사용 금지
- 비공개 Graph 관계 사용 금지
- 미공개 사건 정답 접근 금지
- 실제 범인 지목 상태 변경 금지

### 4.3 Hint Agent

**목적:** 현재 조사 상태에 적합한 단계별 힌트를 제공합니다.

담당 기능:
- 현재 챕터와 증거 수집 현황 분석
- 조사 방향 안내
- 보유 증거 간 관계 안내
- 다음 조사 행동 제안

제한사항:
- 미해금 챕터 관련 내용 공개 금지
- 미획득 증거의 내용 공개 금지
- 직접적인 범인 및 엔딩 정답 제공 금지
- GameState 직접 변경 금지

초기에는 규칙 기반 힌트를 우선 구현합니다.

## 5. Agent 공통 실행 계약

### 5.1 AgentType

허용되는 Agent 유형은 다음과 같습니다.

- `npc`
- `deduction`
- `hint`

### 5.2 AgentRequest

플레이어의 요청 데이터를 표현합니다.

주요 필드:
- `agent_type`
- `message`
- `presented_evidence_id`

보안 규칙:
- session_id 및 case_id를 클라이언트 요청 계약에 포함하지 않습니다.
- 허용된 Agent 유형만 사용합니다.
- 메시지 길이는 최대 200자입니다.
- 증거 제시는 NPC Agent에서만 허용합니다.

### 5.3 AgentContext

서버에서 생성하는 게임 상태 스냅샷입니다.

주요 필드:
- `session_id`
- `case_id`
- `revision`
- `phase`
- `current_chapter`
- `unlocked_characters`
- `collected_evidence_ids`
- `active_character_id`

`AgentContext.from_game_state()`로 GameState에서 필요한 필드만 추출합니다.

주의사항:
- AgentContext는 인증 토큰이나 권한 증명 자체가 아닙니다.
- FastAPI의 세션 소유권 검증을 통과한 뒤 생성해야 합니다.
- AgentContext의 생성자나 JSON 입력을 외부에 직접 공개하지 않습니다.
- 스냅샷 생성 이후 최신 revision 확인이 필요한 요청은 서버에서 재검증합니다.
- 내부 세션 식별자를 LLM 프롬프트나 공개 응답에 그대로 전달하지 않습니다.

### 5.4 AgentResult

Agent의 내부 실행 결과입니다.

주요 필드:
- `agent_type`
- `text`
- `source_ids`

AgentResult는 내부 결과이며, 외부 응답 전에 허용된 근거와 출력 내용을 추가로 검증해야 합니다.

현재 공통 모델 자체는 `source_ids`의 게임 접근 권한을 확인하지 않습니다.

### 5.5 AgentExecutor

공통 실행 인터페이스는 `Protocol`을 사용합니다.

```python
class AgentExecutor(Protocol):
    @property
    def agent_type(self) -> AgentType: ...

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> AgentResult: ...
```

기존 NPC 엔진과의 호환성을 고려하여 초기에는 동기 실행 계약을 적용합니다.

추후 비동기 호출이 필요하면 서비스 경계에서 실행 방식을 검토합니다.

## 6. Agent별 MCP Tool 접근 정책

아래 표는 향후 MCP 연동을 위한 **권한 설계안**입니다. 아직 MCP Tool이 실제로 구현되거나 권한 검증이 완료된 상태는 아닙니다.

| Tool | NPC | Deduction | Hint |
|---|---|---|---|
| `get_game_context` | 제한 허용 | 허용 | 허용 |
| `search_authorized_evidence` | 제한 허용 | 허용 | 허용 |
| `get_npc_knowledge` | 현재 NPC만 | 거부 | 거부 |
| `get_investigation_progress` | 기본 거부 | 허용 | 허용 |

모든 허용은 서버의 세션 검증, 콘텐츠 승인 정책, 게임 상태 접근 정책 통과를 전제로 합니다.

NPC Agent의 기존 RAG 기능을 MCP Tool로 중복 구현하지 않으며, 필요 시 기존 승인된 검색 경로를 Adapter로 제공합니다.

## 7. Orchestrator 설계 원칙

후속 이슈 #130에서 구현합니다.

### 실행 순서

1. FastAPI에서 플레이어 세션 소유권 검증
2. 서버 저장소에서 최신 GameState 로딩
3. 요청 Agent 유형 검증
4. AgentContext 생성
5. 명시적으로 등록된 Agent 선택
6. Agent 실행
7. 결과 및 근거의 공개 권한 검증
8. 필요한 경우 GameState revision 재검증
9. 외부 응답 반환

NPC Agent의 상태 변경은 기존 원자적 대화 실행 경로에서 처리합니다.

읽기 전용 Agent 실행은 서버 상태를 변경하지 않습니다.

### 실패 처리

- 미인증 세션: 접근 거부
- 지원하지 않는 Agent: 요청 거부
- 접근 권한 없는 증거: 공개 금지
- 게임 상태 불일치: 실행 중단 또는 안전한 재검증
- Django 서비스 장애: 미승인 정보 공개 금지
- LLM 응답 검증 실패: 검증되지 않은 내용 반환 금지

## 8. LangGraph 도입 판단

### Day 4 결정: 초기 구현에서는 필수 도입하지 않음

**근거**

1. 기존 NPC 대화 및 게임 진행 로직이 이미 구현되어 있습니다.
2. 최초 MVP는 명시적인 요청 유형 기반 라우팅으로 구성할 수 있습니다.
3. LangGraph 도입보다 Agent 간 역할 분리 및 권한 검증이 우선입니다.
4. 새로운 워크플로 엔진을 즉시 도입하면 기존 대화 저장 흐름과 중복될 위험이 있습니다.

### 후속 도입 검토 기준

- Agent 간 반복적인 실행과 피드백이 필요한 경우
- 여러 Agent가 순차적으로 추론 결과를 검증하는 경우
- 조건부 분기가 복잡해지는 경우
- 실행 중단 및 재개 기능이 필요한 경우
- 명시적 라우팅으로 유지보수하기 어려운 워크플로가 확인되는 경우

LangGraph를 도입하더라도 기존 인증·권한·GameState 저장 경계를 유지합니다.

## 9. 보안 및 안정성

### 9.1 권한 경계

- 세션 소유권: FastAPI
- 콘텐츠 승인: Django
- 플레이어 해금 상태: GameState 및 기존 정책 엔진
- 게임 상태 변경: 기존 게임 서비스
- Agent 실행: Orchestrator
- MCP Tool 공개 범위: 서버 정책 기반 허용 목록

### 9.2 주요 보안 요구사항

- 프롬프트 인젝션에 의한 권한 상승 금지
- LLM에 서비스 토큰 제공 금지
- 비공개 CASE-001 정답 데이터 전달 금지
- 미해금 증거·관계 데이터 공개 금지
- Tool 입력에 포함된 식별자를 권한의 근거로 사용하지 않음
- 게임 상태 변경의 원자성 및 revision 검사 유지
- 승인되지 않은 결과는 기본 거부

## 10. Issue #129 테스트 현황

| 항목 | 결과 |
|---|---|
| AgentRequest 입력 검증 | PASS |
| AgentType 제한 | PASS |
| 클라이언트 권한 필드 차단 | PASS |
| NPC 증거 제시 제한 | PASS |
| AgentContext 생성 | PASS |
| 미해금 NPC 차단 | PASS |
| Context 스냅샷·불변성 | PASS |
| AgentResult 생성 | PASS |
| AgentExecutor 인터페이스 | PASS |
| 단위 테스트 | 19 PASS |
| Ruff | PASS |

검증 환경:
- Python 3.13.15
- Pydantic 2.14.2
- pytest 9.2.0

위 결과는 현재까지 실행한 계약 단위 테스트의 결과입니다.

전체 FastAPI·Django 회귀 테스트와 실제 Agent–MCP 통합 테스트는 아직 수행하지 않았습니다.

## 11. 후속 개발

| 이슈 | 작업 |
|---|---|
| #130 | Agent Orchestrator 기본 구현 |
| #131 | NPC Agent Adapter |
| #132 | Deduction Agent |
| #133 | Hint Agent |
| #134 | MCP Server 및 읽기 전용 Tool |
| #135 | 통합 테스트 및 문서화 |

## 12. 결론

Issue #129에서는 Multi-Agent 도입을 위한 공통 데이터 계약, 실행 인터페이스와 권한 경계를 정의합니다.

기존 FastAPI·Django·Hybrid RAG를 유지하고, Agent별 책임을 분리하여 후속 개발에서 기존 기능을 중복 구현하지 않도록 합니다.

최종 구조에서는 LLM이나 개별 Agent가 권한을 결정하지 않으며, 서버가 검증한 게임 상태와 콘텐츠 공개 정책을 기반으로 Agent와 MCP Tool을 실행합니다.