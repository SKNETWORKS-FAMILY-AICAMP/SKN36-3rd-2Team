# 기존 코드베이스 및 FastAPI 아키텍처 분석

## 1. 작업 정보

- 날짜: 2026-11-20
- GitHub Issue: #91
- 브랜치: feature/91-backend-analysis
- 기준 커밋: 53f6872
- 목적: 4차 프로젝트를 위한 기존 백엔드 분석

## 2. 개발 환경

| 기술 | 버전 |
|---|---|
| Python | 3.13.15 |
| uv | 0.12.2 |
| FastAPI | 0.162.2 |
| Pydantic | 2.14.2 |
| Pydantic Settings | 2.16.2 |
| Neo4j Driver | 6.4.1 |
| Qdrant Client | 1.16.0 |
| Ollama | 0.6.3 |
| pytest | 9.2.0 |

버전은 로컬 개발 환경에서 확인했습니다.

## 3. 주요 모듈

| 디렉터리 | 주요 책임 |
|---|---|
| api | FastAPI 엔드포인트 및 런타임 초기화 |
| scenario | 게임 진행, 증거, 지목, 접근 정책 |
| trigger | NPC 대화 및 상태 변경 처리 |
| chat | NPC 페르소나, 대화 및 LLM 연동 |
| retriever | Dense, BM25, Graph, Hybrid RAG |
| db | Qdrant 및 Neo4j 연동·데이터 적재 |
| ingest | 데이터 로딩, 청킹 및 임베딩 |

기존 engine 디렉터리는 현재 실질적인
게임 엔진 구현의 중심이 아닙니다.

## 4. FastAPI 진입점

파일:
backend/src/crimescene/api/main.py

- 환경변수 로딩
- SQLiteCase001Repository 초기화
- create_app()을 통한 API 생성
- RAG 런타임 수명주기 관리
- 비공개 사건 정답 데이터 별도 로딩

핵심 라우터:
backend/src/crimescene/api/app.py

## 5. 기존 API

| Method | Endpoint | 역할 |
|---|---|---|
| POST | /api/games | 게임 생성 |
| GET | /api/games/{session_id} | 상태 조회 |
| POST | .../prologue/complete | 프롤로그 완료 |
| POST | .../characters/{character_id}/select | NPC 선택 |
| GET | .../chats/{character_id} | 대화 기록 |
| POST | .../chat | NPC 대화 |
| POST | .../evidence/{evidence_id}/collect | 증거 획득 |
| GET | .../evidence | 증거 목록 |
| GET | .../evidence/available | 획득 가능 증거 |
| GET | .../evidence/{evidence_id} | 증거 상세 |
| GET | .../evidence/{evidence_id}/photo | 증거 이미지 |
| GET | .../progress | 진행률 |
| GET | .../relationships | 인물 관계 |
| POST | .../accusations | 범인 지목 |
| GET | .../ending | 엔딩 조회 |

...은 /api/games/{session_id}를 의미합니다.

## 6. 게임 상태 및 데이터 저장

주요 구현:
- GameState: Pydantic 기반 상태 모델
- SQLiteCase001Repository: 게임 상태 저장
- SQLiteNPCSessionRepository: NPC 대화 저장
- revision: 상태 변경 동시성 검증
- HMAC 쿠키: 세션 소유권 검증

확인된 SQLite 테이블:
- game_states
- npc_sessions
- npc_exchanges

게임 상태와 NPC 대화는 SQLite 트랜잭션을
통해 일관성을 유지하도록 구현되어 있습니다.

## 7. RAG 및 AI

확인된 구성:
- Qdrant Dense Retrieval
- BM25 Sparse Retrieval
- RRF 검색 결과 결합
- Neo4j Graph Retrieval
- 게임 상태 기반 검색 접근 제어
- NPC별 RAG 컨텍스트 구성

관련 구현:
- retriever/hybrid_search.py
- retriever/authorized_hybrid_search.py
- chat/npc_rag_service.py

## 8. 재사용 대상

- 기존 FastAPI 라우트
- SQLite 게임 상태 저장소
- NPC 대화 및 세션 처리
- 증거 획득과 해금 정책
- 범인 지목 및 엔딩 처리
- Hybrid RAG 검색 모듈
- NPC 지식 접근 제한 로직
- 기존 자동화 테스트

## 9. 확장 시 주의사항

1. 기존 /api/games 경로 유지
2. 게임 상태의 단일 관리 주체 유지
3. 현재 E01~E10으로 제한된 입력 검증 확장 필요
4. TOTAL_SCORE=21 하드코딩 검토
5. chapter, objective 등 신규 상태 필드 설계 필요
6. 기존 SQLite 저장 상태와 하위 호환성 유지
7. Django ORM의 기존 게임 상태 직접 수정 방지
8. Django와 FastAPI 인증 및 DB 책임 분리 필요

위 항목은 분석 결과와 확장 요구사항이며
아직 구현 완료된 기능이 아닙니다.

## 10. 기존 기능 테스트

실행 명령:

python -m pytest -q
  tests/test_issue27_game_progress.py
  tests/test_issue27_state_repository.py
  tests/test_issue62_game_api.py

실행 결과:
- Passed: 23
- Failed: 0
- Duration: 5.21s

검증 범위:
- 초기 게임 상태
- 진행 단계 전환
- SQLite 상태 저장 및 복구
- 게임 생성 및 이어하기
- 세션 소유권 검증
- NPC 선택 및 접근 제한

전체 테스트 스위트 및 외부 서비스 연동 테스트는
이번 실행 범위에 포함되지 않았습니다.

## 11. 후속 분석 및 작업

- 전체 API 요청·응답 계약 상세 분석
- Django/FastAPI 책임 범위 확정
- 콘텐츠 DB 모델 및 서비스 연동 설계
- API 계약 v3.0 작성
- Django 초기 프로젝트 구성
- 전체 회귀 테스트 및 성능 평가

## 12. 현재 결론

기존 게임 엔진과 Hybrid RAG를 재사용하고,
Django + DRF는 콘텐츠 관리 및 운영 API를
담당하도록 분리하는 방향을 우선 검토합니다.

최종 아키텍처는 별도 설계 이슈에서 확정합니다.
