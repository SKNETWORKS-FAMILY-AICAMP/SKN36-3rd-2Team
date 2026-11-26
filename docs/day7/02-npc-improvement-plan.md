# Day 7 - NPC Dialogue Improvement Plan

## 1. 개선 목표

NPC를 단순한 문서 인용 시스템에서
게임 상태와 캐릭터 특성을 반영하는 대화형 조사 대상으로 고도화한다.

## 2. 구현 이슈

| Issue | Scope | Priority |
|---|---|---|
| #171 | Persona, Intent Router, Natural Dialogue | P0 |
| #172 | Conversation Memory, History Consistency | P0 |
| #173 | Emotion, Trust, Pressure Reaction | P0 |
| #174 | Evidence Reaction, Dialogue Strategy | P1 |
| #175 | Context-aware Hybrid RAG, MCP | P1 |
| #176 | Security and Regression Tests | P0 |

## 3. #171 - Persona and Dialogue Routing

- 캐릭터별 승인된 Persona 정보 확장
- 안전한 일상 대화와 사건 관련 질문 분리
- 캐릭터 관점의 자연스러운 표현
- 질문 의도 및 관련성 검증
- 불필요한 EMPTY_QUOTES 재호출 감소

## 4. #172 - Conversation Memory

- 기존 SQLite 대화 이력 재사용
- 최근 대화 기반 후속 질문 처리
- 플레이어 질문 회상 지원
- NPC별 진술 이력 분리
- 이전 진술의 현재 권한 재검증
- 화면용 응답과 조회 이력 일관성 검토

## 5. #173 - Emotional State

- NPC별 감정 및 경계 상태
- 반복 질문과 심리적 압박 반응
- 서버 관리 상태 검증
- 감정 상태와 정보 접근 권한 분리

## 6. #174 - Evidence-aware Dialogue

- 수집된 증거 및 제시 가능 NPC 검증
- 증거 종류별 반응 전략
- 제시 이력에 따른 반응 변화
- 기존 트리거 및 승인된 진행 조건 유지

## 7. #175 - Context-aware RAG and MCP

- 이전 질문을 활용한 검색 문맥 확장
- 질문 관련성 개선
- 불필요한 검색 및 생성 호출 감소
- 필요성이 검증된 읽기 전용 MCP 도구 연동
- 기존 PolicyEvaluator 및 Tool Allowlist 유지

## 8. #176 - Security and Regression

- 미수집 증거 공개 방지
- 미승인 NPC 카드 공개 방지
- Prompt Injection 방어
- 세션 간 정보 격리
- 챕터 및 NPC 접근 권한 검증
- 기존 GameState 및 Revision 무결성 유지
- 기존 API 계약 호환성 유지

## 9. Proposed Acceptance Targets

| Metric | Baseline | Target |
|---|---:|---:|
| Normal Fallback Rate | 55% | <= 10% |
| Mean Engine Latency | 2.212s | <= 3s |
| Max Engine Latency | 6.1496s | <= 8s |
| History Count Match | 100% | 100% |
| Follow-up Non-fallback Rate | 40% | >= 90% |
| Memory Non-fallback Rate | 0% | >= 90% |
| Security Refusal Fixtures | 20/20 | 20/20 |
| Unauthorized Disclosure | Full audit pending | 0 |
| Weighted Quality Score | Pending | >= 85/100 |

Non-fallback은 실제 질문 해결률과 동일하지 않다.
별도의 정성 평가를 수행한다.

목표 수치는 제안된 개발 목표이며 달성 결과가 아니다.
답변할 권한이 없는 질문에는 안전한 거부를 유지한다.

## 10. A/B Evaluation Protocol

- 동일한 평가 질문 및 순서
- 동일한 모델과 생성 설정
- 동일한 콘텐츠 및 릴리스
- 동일한 GameState Fixture 조건
- NPC별 독립 세션
- 동일한 승인 정책
- 응답 시간 및 생성 함수 호출 횟수 비교
- 질문 관련성 및 사실 정확성 별도 평가

가급적 복수 반복 실행으로 변동성을 확인한다.

기존 Baseline 스크립트와 질문 목록은 비교군으로 보존한다.

## 11. Weighted Quality Rubric

| Category | Weight |
|---|---:|
| Naturalness | 20 |
| Persona Consistency | 15 |
| Conversation Memory | 15 |
| Factual Accuracy | 15 |
| Emotional Expression | 10 |
| Evidence Reaction | 10 |
| Context Understanding | 10 |
| Conciseness | 5 |

총점 100점.

실제 증거 제시 시나리오를 추가한 후 전체 배점을 평가한다.
접근 제어 위반은 총점과 관계없이 실패 처리한다.

## 12. Mandatory Constraints

- 기존 FastAPI API 계약 유지
- 승인된 원문 및 출처 검증 유지
- 비공개 자료의 자유 생성 금지
- LLM 생성 결과만으로 게임 진행 상태 변경 금지
- NPC 감정 상태를 통한 접근 권한 우회 금지
- E26-A/B/C 접근 범위 유지
- E07 및 E30 미승인 상태 존중
- 서비스 토큰, API Key, SQLite 및 원본 콘텐츠 커밋 금지
- 변경 이슈별 구현, 테스트 및 PR 수행