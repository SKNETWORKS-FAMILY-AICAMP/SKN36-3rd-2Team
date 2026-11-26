# Day 8 - Backend Development Handover

## 1. Day 7 완료 기준

상위 이슈: #169

| Issue | Description |
|---|---|
| #170 | NPC dialogue baseline |
| #171 | Dynamic persona |
| #172 | Conversation memory |
| #173 | Emotional state |
| #174 | Evidence dialogue |
| #175 | Context-aware RAG and MCP review |
| #176 | Security and integration regression |
| #191 | Protected ending image API |
| #192 | E30 consent API |

#176 병합 후 Day 7 전체 완료로 처리한다.

## 2. 현재 시스템 구성

- FastAPI: 게임 및 대화 API
- Django: 콘텐츠 관리 및 승인
- SQLite: GameState 및 대화 기록
- Qdrant: Dense and BM25 retrieval
- Neo4j: Graph retrieval
- Ollama: BGE-M3 embedding
- OpenAI: NPC dialogue generation
- Multi-Agent: NPC, Deduction, Hint
- MCP: 승인된 Tool 실행

### Local services

| Service | Port |
|---|---:|
| FastAPI | 8000 |
| Django | 18004 |
| Qdrant | 6333 |
| Neo4j HTTP | 7474 |
| Neo4j Bolt | 7687 |
| Ollama | 11434 |

## 3. 현재 데이터 기준

- Case: CASE-001
- Runtime: case001_1120
- Release: v0.15.0
- Scope: LOCAL_INTEGRATION_TEST
- Collection: case001_rag_1120_revision2

| Data | Count |
|---|---:|
| Evidence rules | 30 |
| Approved evidence | 28 |
| RAG records | 138 |
| Valid dense vectors | 138 |
| Valid sparse vectors | 138 |
| Graph nodes | 42 |
| Graph edges | 111 |
| Published graph edges | 0 |
| Published NPC cards | 32 |
| Blocked NPC cards | 77 |
| Published documents | 28 |
| Unpublished documents | 1 |

E07 및 E30은 일반 승인 증거 목록에 포함되지 않는다.

실제 콘텐츠 승인 범위는 서버 Release에서 결정한다.

## 4. Day 8 성능 기준선

### General NPC evaluation

| Metric | Baseline |
|---|---:|
| Normal fallback | 26.25% |
| Factual grounded | 47.5% |
| Mean latency | 1.016s |
| Median latency | 1.282s |
| Max latency | 10.730s |
| LLM calls | 57 |
| Extra LLM calls | 0 |
| Security exact fallback | 20/20 |
| Display mismatch | 0 |

### Evidence dialogue evaluation

| Metric | Baseline |
|---|---:|
| Normal fallback | 18.52% |
| Factual grounded | 7/12 |
| Mean latency | 0.984s |
| LLM calls | 16 |
| Extra LLM calls | 1 |
| Generic pressure clarification | 12/12 |
| Unauthorized presentation denied | 5/5 |

두 평가 데이터는 시나리오가 다르므로
하나의 성능 지표로 합산하지 않는다.

## 5. Day 8 최우선 개선 과제

### P0 - Grounded response 회복

사건 사실 확인 성능이 65%에서 47.5%로 하락하였다.

개선 대상:

- B04 피해자와의 관계
- B05 이전 답변 후속 질문
- B07 반복 질문

확인할 요소:

- EMPTY_QUOTES 발생 원인
- 승인 컨텍스트와 질문 관련성
- 제한적 재시도 정책
- POST_GENERATION_REJECTION
- 검증된 반복 응답 재사용 조건
- 후속 질문 검색 질의 확장

보안을 완화하여 Grounded 비율을 높이지 않는다.

### P0 - 반복 A/B 테스트

동일 NPC, 질문, 초기 GameState, 모델 설정,
승인 데이터 및 평가 기준을 사용한다.

비교 대상:

- 기존 응답 생성 정책
- 제한적 재시도 정책
- Context-aware Query
- 후속 질문 검색 개선

정상 대화와 사실 확인 성능을 분리하여 평가한다.

보호 정보 유출은 Hard Gate로 처리한다.

### P1 - Hybrid RAG 최적화

- C04 및 C08 BM25 매칭 부족 원인 분석
- 승인 원본의 검색 적합성 검토
- Dense와 BM25의 RRF 기여도 비교
- Original Graph Query 분리 검증
- 승인된 Graph 관계 활용 가능성 검토

Graph 관계는 별도의 콘텐츠 승인 없이 공개하지 않는다.

### P1 - MCP 통신 성능

기존 프로파일:

- Deduction synchronous mean: 0.622ms
- Hint synchronous mean: 0.646ms

실제 MCP SDK 통신 구간은 기록되지 않았다.

측정 대상:

- 연결 초기화
- Tool 호출
- 응답 검증
- Timeout
- Connection cleanup
- Agent collaboration

보안 상태 재검증을 임의로 제거하지 않는다.

### P1 - 최대 응답 지연 분석

첫 NPC 자기소개 응답에서 10.73초가 관찰되었다.

검색 초기화, BM25 형태소 분석 초기화,
임베딩 및 모델 호출 구간을 분리 측정한다.

Cold start 원인은 아직 확정되지 않았다.

### P1 - BM25 복구 운영 계약

기존 일회성 복구 스크립트는 사용 이력이 확인되었다.

향후 Sparse Vector가 다시 누락되었을 경우,
새로운 fail-closed 부트스트랩과의 호환성을 확인한다.

신뢰된 Dataset과 공용 Qdrant 동기화 경로를
사용하는 운영 복구 절차를 별도로 검증한다.

## 6. 권장 Day 8 품질 목표

아래 수치는 확정된 실측값이 아닌 개선 목표이다.

| Metric | Current | Target |
|---|---:|---:|
| Normal fallback | 26.25% | <= 20% |
| Factual grounded | 47.5% | >= 70% |
| Mean latency | 1.016s | <= 1.5s |
| Unauthorized disclosure | 0 observed | 0 |
| Display mismatch | 0 | 0 |
| Regression failures | 0 | 0 |

실제 MCP 성능 목표는 통신 기준선 측정 이후 확정한다.

## 7. 기존 계약 유지

- FastAPI 기존 API 경로 및 필드 의미 유지
- Django 승인 절차 유지
- E26 구획별 접근 정책 유지
- E30 별도 동의 및 승인 유지
- 기존 지목 횟수 및 엔딩 판정 유지
- 비승인 RAG 및 Graph 데이터 공개 금지

## 8. 작업 순서

1. 반복 A/B 테스트 환경 구축
2. 사실 확인 Grounded 성능 개선
3. Hybrid RAG 검색 품질 최적화
4. 실제 MCP 통신 성능 측정
5. 공격 시나리오 확대
6. 자연 플레이 E2E 검증
7. 전체 백엔드 회귀
8. API 계약 및 배포 문서 정리

## 9. Git 작업 원칙

- GitHub Issue 단위로 진행
- GitHub에서 작업 브랜치 생성
- dev 직접 수정 금지
- 테스트 통과 후 Commit
- 명시적 파일 Staging
- PR 본문에 Closes 이슈 번호 작성
- 병합 후 다음 이슈 진행

기존 E26 감사 계약 문서는 삭제하거나
의도하지 않게 Commit하지 않는다.

## 10. 일정

- 2026-11-29: Day 8 개발 및 최종 품질 개선
- 2026-11-30: 프론트엔드 통합 및 배포
- 2026-12-01: QA 및 장애 수정
- 2026-12-02: 개발 완료 및 코드 동결
- 2026-12-03: 발표 준비
- 2026-12-04: 최종 발표

상기 일정은 개발 계획이며 완료 실적이 아니다.