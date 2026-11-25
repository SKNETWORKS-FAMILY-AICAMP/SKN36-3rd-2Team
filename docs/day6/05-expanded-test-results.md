# Day 6 - Final Test Results

## 1. 자동화 테스트 결과

| Suite | Passed | Failed | Time |
|---|---:|---:|---:|
| FastAPI Regression | 2617 | 0 | 70.24s |
| Django | 225 | 0 | 12.552s |
| Live Integration | 14 | 0 | 17.77s |
| Neo4j Sync | 6 | 0 | 14.42s |
| Ollama | 3 | 0 | 3.17s |
| Total | 2865 | 0 | 118.152s |

- 최종 미실행 테스트: 0
- 최종 실패 테스트: 0
- 누적 통과율: 100%

최초 pytest에서 Skip된 23개는 별도 환경에서 모두 실행하였다.
전체 수치는 개별 테스트 실행 결과의 합산이다.

## 2. 별도 Live 검증

| Scenario | Result |
|---|---|
| v0.14.0 Release HTTP | PASS |
| v0.15.0 Release HTTP | PASS |
| Expanded Runtime Smoke Test | PASS |
| Chapter and Gameplay Integration | PASS |
| Live RAG and MCP Integration | PASS |
| Django Approval Isolation | PASS |
| Original Database Preservation | PASS |
| Temporary Server Cleanup | PASS |
| Neo4j Test Container Cleanup | PASS |

위 별도 스크립트 검증은 2865개 수치에 추가하지 않았다.

## 3. 외부 서비스 검증

- 실제 Dense 및 Sparse 검색
- MCP 증거 검색
- Deduction Agent API
- Hint Agent API
- Assist Agent API
- 인증 토큰 검증
- Revision 및 세션 격리
- HTTP 연결 장애
- HTTP Read Timeout
- Graph 접근 정책
- NPC Graph 지식 범위
- Neo4j 동기화 및 Rollback

14개 외부 서비스 테스트의 대상은 기존 Runtime이다.
v0.15.0은 별도 Live 스크립트를 통해 검증하였다.

## 4. 테스트 환경

- Windows
- Python 3.13.15
- pytest 9.2.0
- Django 5.2.19
- Qdrant
- Neo4j
- Ollama BGE-M3

## 5. 검증 제외 범위

- 운영 환경 부하 및 스트레스 테스트
- 전체 프론트엔드 플레이 테스트
- 모든 NPC의 LLM 생성 품질
- 신규 Graph 관계 공개
- 정식 콘텐츠 발행 승인
