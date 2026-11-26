# Day 7 - NPC Dialogue Integration Regression

## 1. 작업 개요

- Issue: #176
- Date: 2026-11-26
- Branch: test/176-npc-dialogue-regression
- Baseline commit: dcaa384
- Case: CASE-001
- Content version: case001_1120
- Release: v0.15.0
- Scope: LOCAL_INTEGRATION_TEST

## 2. 개발 목적

Day 7에서 개발한 NPC 대화 시스템의 개별 기능이
실제 통합 환경에서 정상적으로 상호작용하는지 검증한다.

운영 코드 변경 없이 통합 테스트 및 보안 평가를 수행한다.

## 3. 소스 및 테스트 인벤토리

| 영역 | 파일 | 함수 |
|---|---:|---:|
| NPC Dialogue | 23 | 83 |
| RAG Security | 27 | 83 |
| Multi-Agent MCP | 19 | 60 |
| Game Integration | 7 | 57 |
| Total | 76 | 283 |

- 관련 테스트 파일: 158
- 관련 테스트 함수: 1348
- 기존 핵심 집중 회귀: 492 passed
- 실행 시간: 7.52초

테스트 함수 수는 pytest parameterization을 포함한
실제 테스트 실행 건수와 구분한다.

## 4. 최종 NPC 아키텍처

### 4.1 대화 처리 계층

1. GameState 및 NPC 선택 검증
2. 질문 의도 분류
3. 안전한 일상 대화 처리
4. 대화 기억 및 반복 질문 처리
5. NPC 감정 상태 계산
6. 공식 증거 제시 검증
7. Context-aware 검색 질의 구성
8. NPC별 Pre-search Access Control
9. Dense, BM25 및 Graph 검색
10. Reciprocal Rank Fusion
11. 최종 승인 근거 구성
12. LLM 원문 인용 생성
13. Output Guard 검증
14. NPC별 자연스러운 말풍선 생성
15. SQLite Atomic Dialogue 저장

일상 대화, 안전한 기억 확인 및 포괄적 추궁은
서버 정의 응답으로 처리할 수 있다.

구체적인 사건 사실은 기존 승인 근거 검증을 요구한다.

## 5. NPC Lifecycle Integration

File:

backend/tests/test_day7_npc_dialogue_integration.py

### 검증 대상

- NPC C01부터 C10까지 전체 10명
- 인사 및 자기소개
- Dynamic Persona
- 검증된 반복 질문 응답 재사용
- 후속 질문의 대화 맥락
- 이전 질문 기억
- NPC 감정 상태 변화
- 연속 추궁 40턴
- SQLite 저장 및 복원
- NPC 간 대화 이력 격리
- 게임 세션 간 대화 이력 격리
- GameState 원본 보존

### 실행 결과

| Metric | Result |
|---|---:|
| NPC cases | 10 |
| Dialogue turns | 110 |
| Passed | 10 |
| Failed | 0 |
| Seconds | 2.95 |

실제 NPC Runtime과 SQLite를 사용한다.
검색 결과와 LLM 생성 응답은 테스트 Fixture를 사용한다.

## 6. Security Integration

File:

backend/tests/test_day7_npc_security_regression.py

| 검증 항목 | Passed |
|---|---:|
| Evidence and Atomic Dialogue lifecycle | 1 |
| Unauthorized LLM quote rejection | 3 |
| Forbidden presentation rollback | 4 |
| E07 and E30 search rejection | 2 |
| Emotional access bypass rejection | 1 |
| Stale revision rejection | 1 |
| Total | 12 |

실행 시간: 79.20초

실제 In-memory Qdrant, Korean BM25, RRF,
접근 정책 엔진 및 SQLite Atomic 저장을 사용하였다.

임베딩과 LLM 생성은 통제된 Fixture를 사용하였다.
실제 Neo4j 통신 성능을 측정한 테스트는 아니다.

초기 실행에서는 Fixture의 NPC 선택 저장 순서가
잘못되어 12개 Setup Error가 발생하였다.

NPC 선택 저장 후 GameState 등록 순서로 수정하여
12개 테스트 전체가 통과하였다.

운영 코드의 Revision 검증은 변경하지 않았다.

## 7. 실제 OpenAI 평가

### 7.1 평가 조건

- Provider: OpenAI
- Model: gpt-5.6-luna
- Requested max tokens: 1024
- NPC: C01-C10
- Chapter: CH00
- Dialogue turns: 100
- Normal turns: 80
- Security turns: 20
- Qdrant: case001_rag_1120_revision2
- Initial evidence: none
- Session storage: in-memory

기존 evaluate_day7_npc_baseline.py를 재사용하였다.

동일한 100개 질문과 NPC 조합을 사용하였으며
기록된 Provider, Model, Content Version,
Release Version 및 Chapter 일치를 확인하였다.

원본 Baseline 파일의 SHA256은 유지되었다.

### 7.2 개선 전후 비교

| Metric | Before | After |
|---|---:|---:|
| Normal turns | 80 | 80 |
| Normal fallback | 44 | 21 |
| Normal fallback rate | 55.00% | 26.25% |
| Normal non-fallback rate | 45.00% | 73.75% |
| Grounded responses | 26 | 19 |
| Mean latency (s) | 2.212 | 1.016 |
| Median latency (s) | 2.312 | 1.282 |
| Max latency (s) | 6.1496 | 10.730 |
| LLM calls | 150 | 57 |
| Extra LLM calls | 60 | 0 |

주요 성과:

- 정상 Fallback 비율 28.75%p 감소
- 평균 응답 시간 약 54.07% 단축
- 전체 LLM 호출 62% 감소
- 추가 LLM 호출 100% 감소

최대 지연시간은 오히려 증가하였다.

### 7.3 시나리오별 비교

| Scenario | Before fallback | After fallback |
|---|---:|---:|
| B01 Greeting | 0/10 | 0/10 |
| B02 Check-in | 10/10 | 0/10 |
| B03 Identity | 0/10 | 0/10 |
| B04 Relationship | 4/10 | 7/10 |
| B05 Follow-up | 6/10 | 7/10 |
| B06 Memory recall | 10/10 | 0/10 |
| B07 Repeat question | 4/10 | 7/10 |
| B08 Pressure | 10/10 | 0/10 |
| B11 Unreleased evidence | 10/10 | 10/10 |
| B12 Prompt injection | 10/10 | 10/10 |

보안 시나리오의 Fallback은 정상적인 방어 결과이며
일반 대화 품질 지표에서 제외한다.

### 7.4 사실 확인 질문 분리 평가

대상: B03, B04, B05, B07

| Metric | Before | After |
|---|---:|---:|
| Factual turns | 40 | 40 |
| Grounded | 26 | 19 |
| Grounded rate | 65.0% | 47.5% |
| Fallback | 14 | 21 |
| LLM calls | 50 | 37 |

사실 확인 Grounded 비율은 17.5%p 하락하였다.

전체 Fallback 감소를 RAG 검색 정확도 증가로
해석해서는 안 된다.

### 7.5 응답 유형

정상 대화 80턴:

- Grounded response: 19
- Safe social dialogue: 20
- Safe memory recall: 10
- Safe pressure clarification: 10
- Fallback: 21

서버 정의 응답은 Grounded로 집계하지 않는다.

### 7.6 NPC별 결과

| NPC | Non-fallback | Fallback | LLM calls |
|---|---:|---:|---:|
| C01 | 6/8 | 2 | 6 |
| C02 | 7/8 | 1 | 5 |
| C03 | 5/8 | 3 | 6 |
| C04 | 5/8 | 3 | 6 |
| C05 | 8/8 | 0 | 5 |
| C06 | 5/8 | 3 | 6 |
| C07 | 7/8 | 1 | 5 |
| C08 | 5/8 | 3 | 6 |
| C09 | 6/8 | 2 | 6 |
| C10 | 5/8 | 3 | 6 |
| Total | 59/80 | 21 | 57 |

C10 호출 수는 전체 집계값과 나머지 NPC 결과로 계산하였다.

### 7.7 최종 보안 검증

- Security turns: 20
- Exact fallback: 20
- Manual review required: 0
- Canonical/display mismatch: 0
- Provider errors: 0
- Conversation history: 100/100
- Matched scenarios: 100/100

이번 평가 시나리오에서 보호 정보 유출은 관찰되지 않았다.

## 8. 전체 백엔드 회귀 테스트

| Framework | Passed | Skipped | Failed |
|---|---:|---:|---:|
| FastAPI | 3148 | 26 | 0 |
| Django | 247 | 0 | 0 |
| Total | 3395 | 26 | 0 |

- FastAPI duration: 159.45s (0:02:39)
- Django duration: 13.892s
- Production code changes: none

집중 테스트와 신규 통합 테스트는 전체 회귀에 포함되므로
중복 합산하지 않는다.

## 9. 평가 자료

- .local/day7_npc_baseline/baseline-20261126-162209-389894.json
- .local/day7_npc_baseline/baseline-20261126-195845-404937.json

평가 원본은 로컬에만 보관한다.

## 10. 평가 한계

- 반복 A/B 테스트가 아닌 단일 개선 전후 비교이다.
- 실제 검색 서비스 및 OpenAI를 사용하지만 게임 상태는 Fixture이다.
- 실제 플레이 전체 흐름 및 브라우저 E2E는 별도 검증 대상이다.
- 전체 Fallback 감소와 사실 확인 성능은 구분해야 한다.
- 실제 MCP SDK 통신 성능은 별도 측정이 필요하다.
- 최대 지연 10.73초의 세부 원인은 확인되지 않았다.

## 11. 결론

NPC 대화 기능의 통합 동작과 보안 회귀를 검증하였다.

응답 효율성과 안전한 대화 처리 기능은 개선되었다.

사실 확인 Grounded 성능 하락을 Day 8의
최우선 품질 개선 과제로 이관한다.