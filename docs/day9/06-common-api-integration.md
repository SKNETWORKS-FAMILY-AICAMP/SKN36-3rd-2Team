# Day 9 - 공통 기능 API 통합 검증

## 1. 작업 개요

| 항목 | 내용 |
|---|---|
| 프로젝트 | 마지막 기록: 졸업하지 못한 밤 |
| 사건 코드 | CASE-001 |
| 작업 일자 | 2026-11-28 |
| GitHub 이슈 | #214 |
| 작업 브랜치 | test/214-common-api-integration |
| 기준 브랜치 | dev |
| 콘텐츠 버전 | case001_1120 |
| 선행 이슈 | #212, #223, #213 |

## 2. 작업 배경

기존 백엔드에는 힌트, 게임 상태 복원, 진행 알림,
스토리 이벤트 조회 및 확인 기능이 각각 구현되어 있다.

이번 작업에서는 개별 기능의 단위 테스트를 넘어
실제 게임 진행 과정에서 각 기능이 정상적으로
연결되는지 검증하는 통합 테스트를 추가하였다.

특히 다음 사항을 중점적으로 확인하였다.

- Multi-Agent 및 MCP 기반 힌트 실행
- 실제 현장 조사를 통한 증거 획득
- 서버 조건 기반 스토리 이벤트 생성
- SQLite 기반 게임 상태 복원
- 스토리 이벤트 확인 및 중복 처리 방지
- 콘텐츠 승인 서비스 장애 시 상태 무결성

## 3. 테스트 환경

| 항목 | 구성 |
|---|---|
| 운영체제 | Windows |
| Python | 3.13.15 |
| pytest | 9.2.0 |
| FastAPI | 실제 애플리케이션 |
| HTTP 요청 | FastAPI TestClient |
| 데이터베이스 | 독립 SQLite 임시 저장소 |
| Hint Agent | 실제 MCPHintAgent |
| Agent Orchestrator | 실제 MCPAgentOrchestrator |
| MCP Client | 실제 실행 경로 |
| MCP Server | 실제 읽기 전용 서버 |
| Django 콘텐츠 승인 | 테스트용 모의 응답 |
| Qdrant 및 Neo4j | 실제 외부 연결 없음 |
| Ollama | 실제 외부 연결 없음 |

이슈 #212에서 작성한 현장 조사 및 챕터 진행
테스트 환경을 재사용하였다.

게임 상태와 획득 증거를 직접 DB에 삽입하지 않고
실제 HTTP 요청을 통해 게임을 진행하였다.

스토리 이벤트 승인 데이터는 테스트용이며
정식 콘텐츠 공개 승인을 의미하지 않는다.

## 4. 검증 대상 API

모든 경로는 /api/games/{session_id} 기준이다.

| Method | 경로 | 기능 |
|---|---|---|
| POST | /agents/hint | 단계별 힌트 |
| GET | / | 게임 상태 조회 |
| GET | /evidence | 획득 증거 조회 |
| POST | /chapter/advance | 챕터 전환 |
| POST | /characters/{character_id}/select | NPC 선택 |
| POST | /investigations/{action_id} | 현장 조사 |
| GET | /story-events/pending | 미확인 이벤트 |
| GET | /story-events/{event_key} | 이벤트 상세 |
| POST | /story-events/{event_key}/ack | 이벤트 확인 |

## 5. 힌트 API 검증

### 5.1 요청 계약

    POST /api/games/{session_id}/agents/hint

요청 예시:

    {
      "level": 2,
      "expectedRevision": 5
    }

| 필드 | 자료형 | 설명 |
|---|---|---|
| level | integer | 1~3단계, 기본값 1 |
| expectedRevision | integer | 현재 게임 Revision |

### 5.2 응답 필드

| 필드 | 설명 |
|---|---|
| agentType | Agent 유형 |
| text | 힌트 안내 문구 |
| sourceIds | 힌트에 사용한 수집 증거 |
| level | 힌트 단계 |
| status | 힌트 처리 상태 |
| chapter | 현재 챕터 |
| collectedCount | 수집 증거 개수 |
| suggestedCharacterId | 추천 NPC 또는 null |
| revision | 검증된 게임 Revision |

### 5.3 단계별 제공 정책

| 단계 | 안내 범위 |
|---|---|
| 1 | 현재 조사 방향 |
| 2 | 수집한 증거 비교 |
| 3 | 공개 NPC 및 수집 증거 활용 |

힌트는 현재 세션의 공개 정보만 사용한다.

미수집 증거는 힌트의 sourceIds에 포함하지 않는다.

추천 NPC는 현재 공개된 NPC 범위로 제한한다.

### 5.4 상태값

| 상태 | 설명 |
|---|---|
| READY | 힌트 제공 가능 |
| NO_EVIDENCE | 수집 증거가 없는 상태 |

증거가 없는 경우에도 공개된 인물과 조사 방향을
안내할 수 있다.

### 5.5 읽기 전용 실행

실제 HTTP 요청은 다음 실행 경로를 사용한다.

    FastAPI
       |
       v
    세션 소유권 및 Revision 검증
       |
       v
    MCPAgentOrchestrator
       |
       v
    MCPHintAgent
       |
       v
    MCP Client
       |
       v
    읽기 전용 MCP Server
       |
       +-- get_game_context
       |
       +-- get_investigation_progress
       |
       v
    검증된 힌트 반환

힌트 실행으로 게임 상태, 수집 점수, NPC 선택 상태
및 Revision이 변경되지 않음을 검증하였다.

현재 구현에는 별도의 힌트 사용 횟수 제한이나
힌트 사용에 따른 점수 차감 정책이 없다.

이번 작업에서는 해당 정책을 추가하지 않았다.

### 5.6 오류 처리

| 조건 | 결과 |
|---|---|
| 프롤로그 중 힌트 요청 | HTTP 409 |
| 이전 Revision | HTTP 409 |
| 범위를 벗어난 level | HTTP 422 |
| 잘못된 자료형 | HTTP 422 |
| 다른 세션 접근 | HTTP 404 |

힌트 응답에는 Cache-Control: no-store를 적용한다.

## 6. 진행 알림 검증

CH01 최초 진입 시 GameResponse.events에 다음
이벤트가 반환되는 것을 확인하였다.

- CHAPTER_CHANGED
- NPC_UNLOCKED 9개
- GAME_PROGRESS_UPDATED

NPC 공개 상태는 #223의 확정 정책에 따라
C01~C10 전체가 유지된다.

GameResponse.events는 해당 요청에서 발생한
일회성 이벤트이며 영속 알림 목록이 아니다.

게임 상태를 재조회하면 events는 빈 배열로 반환된다.

### 6.1 현장 조사 알림

현장 조사 API는 GameResponse 전체를 반환하지 않는다.

다음 응답 필드를 기준으로 증거 획득 알림을 처리한다.

- evidenceId
- created
- score
- total
- revision

created가 true인 경우 신규 증거 획득으로 처리한다.

created가 false인 중복 조사에서는 신규 획득 알림을
반복하여 표시하지 않는다.

## 7. 스토리 이벤트 통합 검증

### 7.1 테스트 이벤트 설정

| 항목 | 내용 |
|---|---|
| Event Key | EVT-CH01-901 |
| Story ID | STORY_020 |
| 챕터 | CH01 |
| 선행 증거 | E19 |
| 필수 플래그 | ACT_RECEPTION_RECORD_INSPECTED |

이벤트 키 및 표시 문구는 테스트 전용이다.

실제 배포 콘텐츠의 이벤트 식별자 또는
정식 승인 문구로 사용하지 않는다.

### 7.2 생성 및 공개 흐름

    현장 조사 요청
          |
          v
    세션 및 Revision 검증
          |
          v
    증거 획득 조건 검증
          |
          v
    증거 및 행동 플래그 반영
          |
          v
    스토리 이벤트 조건 평가
          |
          v
    Django 승인 응답 검증
          |
          v
    이벤트 대기열 구성
          |
          v
    SQLite 원자적 상태 저장
          |
          v
    미확인 이벤트 조회 가능

증거 획득과 이벤트 대기열 반영이 한 번의
Revision 증가로 처리되는 것을 확인하였다.

중복 조사 요청 시 동일한 이벤트를 중복 생성하지
않으며 점수와 Revision도 증가하지 않는다.

### 7.3 미확인 이벤트 조회

    GET /api/games/{session_id}/story-events/pending

응답 구조:

    {
      "items": [
        {
          "eventKey": "EVT-CH01-901",
          "chapter": "CH01",
          "title": "테스트 접수 기록 확인",
          "text": "테스트용으로 승인된 스토리 안내입니다."
        }
      ]
    }

공개 가능한 미확인 이벤트만 반환한다.

선행 조건을 충족하지 않았거나 이미 확인한
이벤트는 목록에 포함하지 않는다.

### 7.4 이벤트 상세 조회

    GET /api/games/{session_id}/story-events/{event_key}

공개 가능한 개별 이벤트의 제목과 본문을 반환한다.

이벤트가 없거나 현재 열람할 수 없는 경우
HTTP 404로 처리한다.

### 7.5 이벤트 확인

    POST /api/games/{session_id}/story-events/{event_key}/ack

별도 요청 Body는 필요하지 않다.

응답 예시:

    {
      "eventKey": "EVT-CH01-901",
      "acknowledged": true,
      "created": true,
      "revision": 7
    }

최초 ACK 성공 시 확인 이력을 저장하고
Revision을 1회 증가시킨다.

중복 ACK에서는 created가 false이며
Revision을 변경하지 않는다.

확인한 이벤트는 미확인 목록에서 제외한다.

## 8. 콘텐츠 승인 실패 검증

| 상황 | HTTP 결과 | 증거 획득 | 이벤트 |
|---|---|---|---|
| 승인 완료 | 200 | 정상 | 대기열 등록 |
| 일반 이벤트 미게시 | 200 | 정상 | 미등록 |
| 승인 서비스 장애 | 503 | 저장하지 않음 | 미등록 |

일반 미게시 이벤트는 노출하지 않으면서
정상적인 증거 획득을 유지한다.

승인 서비스 장애가 발생하면 증거 획득과
스토리 이벤트 저장을 모두 진행하지 않는다.

테스트 전후 GameState 비교를 통해 부분 저장이
발생하지 않음을 확인하였다.

보호 콘텐츠의 특수 승인 규칙은 기존 정책을 유지한다.

## 9. 세션 복원 검증

같은 SQLite 파일을 사용하는 새로운 저장소 객체와
새로운 FastAPI 애플리케이션을 생성하였다.

기존 세션의 소유권 쿠키와 세션 서명 설정을 유지하고
필요한 런타임 설정을 테스트 환경에서 다시 구성하였다.

### 9.1 복원 대상

| 항목 | 결과 |
|---|---|
| 세션 ID | 유지 |
| 현재 챕터 | 유지 |
| 공개 NPC 10명 | 유지 |
| 선택 NPC | 유지 |
| 획득 증거 | 유지 |
| 수집 점수 | 유지 |
| Revision | 유지 |
| 미확인 스토리 이벤트 | 유지 |
| 확인한 이벤트 기록 | 유지 |
| 일회성 진행 이벤트 | 재반환하지 않음 |

### 9.2 이벤트 복원 시나리오

1. 실제 현장 조사로 증거를 획득한다.
2. 승인된 스토리 이벤트를 대기열에 저장한다.
3. NPC를 선택한다.
4. 새 저장소 및 FastAPI 객체를 구성한다.
5. 기존 쿠키로 게임 상태를 조회한다.
6. 미확인 스토리 이벤트를 복원한다.
7. 이벤트 ACK를 처리한다.
8. 중복 ACK의 멱등성을 검증한다.
9. 다시 연결하여 확인한 이벤트의 재표시를 차단한다.

새 애플리케이션 객체 및 저장소를 통해
영속 상태 복원을 검증하였다.

실제 운영 서버 프로세스 종료 및 재기동 테스트는
이번 작업 범위에 포함하지 않는다.

## 10. 프론트엔드 연동 지침

### 10.1 새로고침 또는 재접속

    GET /api/games/{session_id}
    GET /api/games/{session_id}/evidence
    GET /api/games/{session_id}/locations
    GET /api/games/{session_id}/objectives
    GET /api/games/{session_id}/story-events/pending

게임 상태 조회 응답의 최신 Revision을 기준으로
프론트엔드 진행 상태를 갱신한다.

미확인 스토리 이벤트는 pending API를 통해
별도로 복원해야 한다.

### 10.2 증거 획득 이후

1. 현장 조사 응답의 created를 확인한다.
2. 신규 증거라면 획득 알림을 표시한다.
3. 최신 Revision과 점수를 반영한다.
4. 게임 상태와 증거 목록을 갱신한다.
5. 장소 및 수사 목표 정보를 갱신한다.
6. 미확인 스토리 이벤트를 조회한다.

### 10.3 스토리 이벤트 확인 이후

ACK 응답에 포함된 Revision을 반영한다.

ACK 성공 이후 미확인 이벤트 목록을 갱신한다.

중복 ACK 요청에 대한 created=false 응답도
정상 응답으로 처리한다.

### 10.4 힌트 요청

최신 게임 Revision과 힌트 단계를 전달한다.

힌트는 읽기 전용이므로 정상 응답으로 인해
게임 진행 상태가 변경되지 않는다.

HTTP 409 발생 시 최신 상태를 조회한 후
필요에 따라 다시 요청한다.

## 11. 신규 테스트 구성

| 테스트 | 검증 내용 | 건수 |
|---|---|---:|
| test_day9_hint_mcp_integration | 1~3단계 실제 MCP 힌트 | 3 |
| test_day9_hint_empty_evidence | 증거 없는 상태 | 1 |
| test_day9_hint_invalid_requests | 비정상 및 타 세션 요청 | 1 |
| test_day9_story_event_and_session_restore | 이벤트 및 영속 상태 복원 | 1 |
| test_day9_story_approval_failure | 미게시 및 서비스 장애 | 2 |
| 합계 | 신규 통합 테스트 | 8 |

## 12. 보안 및 상태 무결성

| 검증 항목 | 결과 |
|---|---|
| 미수집 증거 힌트 인용 | 차단 |
| 비공개 NPC 추천 | 차단 |
| 다른 세션 힌트 요청 | 차단 |
| 이전 Revision 요청 | 차단 |
| 잘못된 힌트 단계 | 차단 |
| 힌트 실행 중 상태 변경 | 없음 |
| 승인되지 않은 이벤트 공개 | 차단 |
| 승인 서비스 장애 시 부분 저장 | 없음 |
| 중복 이벤트 등록 | 방지 |
| 중복 ACK 상태 변경 | 방지 |
| 확인한 이벤트 재표시 | 방지 |
| SQLite 상태 복원 | 통과 |

## 13. 전체 백엔드 회귀 테스트

| 항목 | 결과 |
|---|---:|
| 통과 | 3201 |
| 실패 | 0 |
| 제외 | 26 |
| 신규 테스트 | 8 |
| 실행 시간 | 142.51초 |

### 13.1 이전 작업 대비 결과

| 이슈 | 통과 건수 | 증가 |
|---|---:|---:|
| #210 | 3161 | - |
| #211 | 3174 | 13 |
| #212 | 3181 | 7 |
| #223 | 3186 | 5 |
| #213 | 3193 | 7 |
| #214 | 3201 | 8 |

### 13.2 제외 사유

| 제외 사유 | 건수 |
|---|---:|
| 실제 외부 서비스 통합 환경 필요 | 14 |
| Windows 심볼릭 링크 사용 불가 | 1 |
| 비공개 엔딩 이미지 선택 실행 | 2 |
| 별도 Neo4j 테스트 환경 필요 | 6 |
| 실제 Ollama 선택 실행 | 3 |
| 합계 | 26 |

## 14. 변경 파일

- backend/tests/test_day9_common_api_integration.py
- docs/day9/06-common-api-integration.md

기존 운영 코드, API 응답 계약, 데이터베이스 스키마
및 프론트엔드 코드는 수정하지 않았다.

## 15. 제한사항 및 후속 작업

- Django 콘텐츠 승인 응답은 테스트용으로 구성하였다.
- 실제 Qdrant, Ollama, Neo4j 연결은 검증하지 않았다.
- 실제 운영 서버 프로세스 재시작은 검증하지 않았다.
- 실제 프론트엔드 화면 및 알림 표시는 검증하지 않았다.
- 실제 NPC 대화 기록의 전체 복원은 별도 검증 대상이다.
- 힌트 사용 횟수 제한 정책은 추가하지 않았다.
- 정식 콘텐츠의 전체 스토리 이벤트 공개 조건은 별도 검증한다.
- 기존 확장판 세션의 NPC 즉시 복구 문제는 별도 검토한다.

## 16. 최종 결과

실제 HTTP 및 MCP 실행 경로를 사용하여 단계별
힌트 기능의 읽기 전용 동작을 확인하였다.

현장 조사에 따른 스토리 이벤트 생성, 조회,
영속 상태 복원 및 ACK 처리를 검증하였다.

신규 통합 테스트 8건을 추가하였으며
전체 백엔드 회귀 테스트 3201건이 통과하였다.

기존 운영 코드의 추가 수정 없이 공통 기능의
통합 테스트 범위를 확대하였다.
