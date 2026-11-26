# Day 7 - NPC Dialogue Baseline

## 1. 평가 목적

Issue #170의 목적은 NPC 대화 엔진의 기존 구조와 한계를 분석하고,
고도화 이후 A/B 테스트에 사용할 정량적 기준값을 확보하는 것이다.

## 2. 평가 환경

| 항목 | 값 |
|---|---|
| Baseline Commit | fa48ef31aed24fb51c1fde45c1555df665f87f9b |
| Content Version | case001_1120 |
| Release Version | v0.15.0 |
| Python | 3.13.15 |
| Django | 5.2.19 |
| FastAPI | 0.162.2 |
| OpenAI SDK | 3.46.0 |
| LLM Provider | OpenAI |
| Model | gpt-5.6-luna |
| Embedding | BGE-M3 |
| Qdrant Collection | case001_rag_1120_revision2 |
| RAG Records | 138 |
| Published NPC Cards | 32 |
| Blocked NPC Cards | 77 |
| Published Evidence | 28 |
| Graph Nodes | 42 |
| Graph Edges | 111 |
| Published Graph Edges | 0 |

## 3. 기존 대화 엔진 구조

FastAPI
-> Agent Orchestrator
-> NPC Agent
-> Atomic Dialogue Engine
-> NPC Chat Runtime
-> Hybrid RAG
-> Authorized Context
-> OpenAI
-> Output Guard
-> Display Rendering
-> SQLite

Hybrid RAG는 Dense Retrieval, BM25, Graph Retrieval 및 RRF를 활용한다.
현재 릴리스에서 승인된 확장 Graph Edge는 0건이다.

NPC Agent는 기존 대화 엔진을 연결하는 Adapter이며,
Deduction 및 Hint Agent는 읽기 전용 MCP 도구를 사용한다.

확인된 NPC 대화 경로에는 직접적인 MCP 호출이 없다.

## 4. 기존 엔진의 한계

- Persona 정보가 제한적이다.
- 일상 대화는 제한된 고정 패턴을 사용한다.
- 사건 관련 응답은 승인된 원문 인용 중심이다.
- 원문 인용 검증은 질문 관련성까지 보장하지 않는다.
- 이전 대화 이력은 검색 이후에 결합된다.
- 후속 질문의 검색 문맥 확장이 부족하다.
- 감정 반응은 규칙 기반이며 지속적인 감정 상태가 없다.
- 화면용 대사와 내부 검증 대사가 분리되어 있다.
- EMPTY_QUOTES에 대해 불필요한 재호출이 발생한다.

## 5. HTTP Pilot Test

실제 FastAPI 서버와 평가 전용 SQLite를 사용하였다.

| 지표 | 결과 |
|---|---:|
| NPC | C01 |
| 평가 턴 | 8 |
| HTTP 성공 | 8 |
| Fallback | 4 |
| Fallback Rate | 50% |
| Mean Latency | 3.459s |
| Min Latency | 0.018s |
| Max Latency | 13.510s |
| History Count | 8 |
| Display/History Mismatch | 1 |

평가 전용 DB 격리를 검증하였다.

## 6. Controlled Engine Baseline

NPC별 독립적인 CH00 Fixture를 구성하였다.
증거 수집, 문서 권한 및 공개 플래그는 임의 부여하지 않았다.

실제 승인된 확장 Runtime과 OpenAI를 사용하였으며,
대화 이력은 인메모리 저장소를 사용하였다.

### 6.1 전체 평가 결과

| 지표 | 결과 |
|---|---:|
| NPC Count | 10 |
| Total Turns | 100 |
| Normal Turns | 80 |
| Security Turns | 20 |
| Normal Fallback Count | 44 |
| Normal Fallback Rate | 55% |
| Grounded Turns | 26 |
| Fixed Social Replies | 10 |
| Security Fallback Count | 20 |
| LLM Generator Calls | 150 |
| Extra Generator Calls | 60 |
| Mean Latency | 2.212s |
| Median Latency | 2.312s |
| Max Latency | 6.1496s |
| History Count | 100 |
| Evaluation Complete | True |

### 6.2 NPC별 결과

| NPC | Normal Fallback | Rate | Grounded | Mean Latency | LLM Calls |
|---|---:|---:|---:|---:|---:|
| C01 | 4/8 | 50% | 3 | 2.350s | 15 |
| C02 | 3/8 | 37.5% | 4 | 2.088s | 14 |
| C03 | 4/8 | 50% | 3 | 2.142s | 14 |
| C04 | 6/8 | 75% | 1 | 3.161s | 17 |
| C05 | 3/8 | 37.5% | 4 | 2.163s | 14 |
| C06 | 4/8 | 50% | 3 | 2.006s | 15 |
| C07 | 3/8 | 37.5% | 4 | 2.056s | 14 |
| C08 | 6/8 | 75% | 1 | 2.086s | 15 |
| C09 | 6/8 | 75% | 1 | 2.087s | 17 |
| C10 | 5/8 | 62.5% | 2 | 1.981s | 15 |

### 6.3 시나리오별 Fallback

| Scenario | Category | Fallback |
|---|---|---:|
| B01 | Greeting | 0/10 |
| B02 | Social Dialogue | 10/10 |
| B03 | Persona | 0/10 |
| B04 | Victim Relationship | 4/10 |
| B05 | Follow-up Context | 6/10 |
| B06 | Conversation Memory | 10/10 |
| B07 | Consistency | 4/10 |
| B08 | Emotional Pressure | 10/10 |
| B11 | Restricted Information | 10/10 |
| B12 | Prompt Injection | 10/10 |

B11과 B12의 안전한 거부 응답은 일반 대화 실패율에서 제외한다.

### 6.4 결과 무결성

- 100개 평가 시나리오 완료
- 중복 NPC/Scenario 조합 없음
- 평가 실행 오류 없음
- Grounded 응답 26건 모두 출처 존재
- 보안 질문 20건 모두 출처 없는 Fallback 반환
- 대화 이력 100건 저장
- Fixture GameState 변경 없음
- Display/Canonical 차이 26건

Display/Canonical 차이는 화면용 렌더링과 내부 검증 응답의
분리 구조에서 발생하며 그 자체를 보안 오류로 판단하지 않는다.

## 7. 정성 분석

- 자기소개가 3인칭 문서 원문으로 반환된다.
- 질문과 무관한 승인 문서가 응답에 포함될 수 있다.
- 피해자와의 관계 질문에 자기소개가 반복된다.
- 이전 질문 회상에 실패한다.
- 후속 질문이 이전 대화의 주제를 유지하지 못한다.
- 심리적 압박에 대한 캐릭터별 반응이 부족하다.

Grounded 여부와 질문 관련성은 별도 지표로 평가해야 한다.

## 8. 재현 방법

기존 Django 콘텐츠 서버 및 검색 인프라를 준비한다.

PowerShell에서 backend/.venv의 Python을 사용한다.

    $env:LLM_PROVIDER = "openai"
    $env:OPENAI_MODEL = "gpt-5.6-luna"
    $env:CRIMESCENE_LLM_MAX_TOKENS = "1024"
    $env:CRIMESCENE_EXPANDED_RELEASE_VERSION = "v0.15.0"

    & .\backend\.venv\Scripts\python.exe -u `
        backend/scripts/evaluate_day7_npc_baseline.py

평가 결과는 .local/day7_npc_baseline에 저장한다.

## 9. 평가 한계

- Controlled Fixture 평가와 자연스러운 게임 진행 E2E는 다르다.
- CH00 조건이 후기 챕터 NPC의 응답 범위를 제한할 수 있다.
- 실제 증거 제시 시나리오는 포함하지 않았다.
- 생성 함수 호출 횟수는 토큰 사용량이나 과금액과 동일하지 않다.
- 보안 질문 20건의 거부는 전체 보안 검증을 의미하지 않는다.
- 100점 기준 정성 점수는 후속 A/B 평가에서 확정한다.
- 승인된 콘텐츠 및 비공개 로컬 자료가 있어야 재현할 수 있다.

## 10. 결론

기존 권한 검증과 원문 인용 검증은 유지하되,
질문 의도 분류, Persona, Conversation Memory, 감정 상태,
증거 반응 및 문맥 기반 검색을 고도화한다.

본 이슈에서는 운영 소스코드를 변경하지 않는다.