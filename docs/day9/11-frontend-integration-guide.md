# Day 9 - 프론트엔드 통합 API 연동 가이드

## 1. 문서 개요

- 프로젝트: 마지막 기록: 졸업하지 못한 밤
- 작업일: 2026-11-28
- 이슈: #218
- 기준 브랜치: dev
- 콘텐츠 버전: case001_1120
- 기준 릴리스: v0.15.0
- 릴리스 범위: LOCAL_INTEGRATION_TEST

본 문서는 Day 9에서 구현하거나 검증한 API와
향후 구현 예정인 API 계약을 구분하여 정리한다.

계약 설계 완료를 실제 API 구현 완료로 해석하지 않는다.

## 2. API 구현 및 연동 상태

모든 아래 경로는 별도 표시가 없는 경우
/api/games/{sessionId}를 기준으로 한다.

| Method | Path | 기능 | 상태 |
|---|---|---|---|
| POST | /api/games | 게임 생성 | 기존 구현 |
| GET | / | 게임 상태 | 사용 가능 |
| POST | /prologue/complete | 프롤로그 완료 | 사용 가능 |
| POST | /chapter/advance | 챕터 전환 | 사용 가능 |
| GET | /content/overview | 공개 콘텐츠 조회 | 기존 구현 |
| GET | /content/scenes/{sceneId} | 공개 장면 조회 | 기존 구현 |
| GET | /locations | 장소 및 조사 권한 | 신규 구현 |
| POST | /investigations/{actionId} | 현장 조사 | 검증 완료 |
| POST | /characters/{characterId}/select | NPC 선택 | 검증 완료 |
| GET | /chats/{characterId} | NPC 대화 이력 | 기존 구현 |
| POST | /chat | NPC 대화 및 단일 증거 제시 | 사용 가능 |
| GET | /evidence | 획득 증거 조회 | 사용 가능 |
| POST | /evidence/{evidenceId}/collect | 증거 획득 | 기존 구현 및 권한 적용 |
| GET | /objectives | 공개 수사 목표 | 확장 완료 |
| POST | /inferences | 증거 기반 추론 | 기존 구현 |
| POST | /agents/hint | 단계별 힌트 | 검증 완료 |
| GET | /story-events/pending | 미확인 이벤트 조회 | 검증 완료 |
| GET | /story-events/{eventKey} | 이벤트 상세 | 검증 완료 |
| POST | /story-events/{eventKey}/ack | 이벤트 확인 | 검증 완료 |
| POST | /consent | 보호 콘텐츠 열람 동의 | 별칭 구현 완료 |
| POST | /reconstruction | 최종 재구성 | 원장 승인 대기 |
| POST | /accusations | 범인 지목 | 원장 승인 대기 |
| POST | /give-up | 수사 포기 | 검증 완료 |
| GET | /ending | 엔딩 조회 | 일부 판정 활성화 대기 |
| GET | /ending/images | 엔딩 이미지 목록 | 기존 구현 |
| GET | /ending/images/{imageIndex} | 엔딩 이미지 | 기존 구현 |
| GET | /timeline | 발견 기반 타임라인 | 계약만 완료 |

사용 가능 상태는 코드 및 해당 테스트 기준이다.
실제 콘텐츠 승인 상태와 플레이어 권한에 따라
개별 기능의 접근 가능 여부가 달라진다.

## 3. 공통 요청 정책

### 3.1 세션 관리

게임 생성 시 반환되는 sessionId를 유지한다.

세션 ID만으로 다른 사용자의 게임에 접근할 수 없다.

브라우저 쿠키 기반 소유권 검증이 적용되므로
기존 인증 쿠키를 유지해야 한다.

Cross-Origin 요청에서 쿠키 전달이 필요한 경우
credentials 설정과 서버 CORS 설정을 확인한다.

### 3.2 Revision 관리

상태 변경 API 중 expectedRevision을 요구하는 요청은
가장 최근 서버 응답의 revision 값을 전달한다.

클라이언트가 revision을 임의 증가시키지 않는다.

HTTP 409 발생 시 최신 게임 상태를 재조회한다.

동일한 상태 변경 요청을 무조건 자동 재전송하지 않는다.

### 3.3 오류 처리

| HTTP | 의미 | 프론트엔드 처리 |
|---|---|---|
| 400 | 잘못된 요청 | 입력 및 요청 확인 |
| 403 | 접근 조건 또는 권한 미충족 | 제한 안내 |
| 404 | 없는 세션 또는 접근 불가 자원 | 조회 대상 확인 |
| 409 | 상태 충돌 또는 진행 조건 불충족 | 최신 상태 재조회 |
| 422 | 입력 스키마 오류 | 요청 필드 검증 |
| 502 | NPC 응답 검증 또는 처리 실패 | 안전한 오류 안내 |
| 503 | 콘텐츠 또는 판정 서비스 준비 불가 | 기능 이용 불가 안내 |
| 504 | 대화 처리 시간 초과 | 사용자 재시도 안내 |

API별 상세 명세가 공통 오류 처리보다 우선한다.

## 4. 장소 및 세부 공간 조회

    GET /api/games/{sessionId}/locations

응답 구조:

- currentChapter
- revision
- locations

장소별 필드:

- id
- accessible
- actions
- subspaces

Action 필드:

- actionId
- available

세부 공간 필드:

- id
- accessible
- actions

### 4.1 현장 장소 매핑

| 장소 ID | 직접 조사 | 세부 공간 |
|---|---|---|
| lobby | 없음 | desk, corridor |
| stairs | inspect-sensor-record | 없음 |
| records | inspect-e13-a | admin |
| office | inspect-e20-a | 없음 |
| security | inspect-emergency-door-record | exit |
| album | inspect-e11-a | student |
| counsel | 없음 | 없음 |

세부 공간과 조사 Action의 상세 매핑은
02-investigation-location-access.md를 참고한다.

프론트엔드는 장소 및 Action의 접근 가능 여부를
서버 응답 기준으로 표시한다.

accessible=true는 모든 하위 Action의 조사 가능을
의미하지 않는다.

available=true인 Action만 정상 조사를 시도한다.

실제 접근 권한은 POST 요청 시 다시 검증된다.

## 5. 현장 조사 처리

    POST /api/games/{sessionId}/investigations/{actionId}

요청 예시:

    {
      "expectedRevision": 12
    }

응답의 주요 필드:

- evidenceId
- created
- score
- total
- revision

created=true는 새로운 획득을 의미한다.
created=false는 이미 처리된 획득일 수 있다.

조사 요청 성공 후에는 최신 게임 상태를 다시 조회한다.

조사 응답에 전체 GameResponse가 포함된다고 가정하지 않는다.

## 6. 챕터 및 NPC 공개

CH00은 프롤로그 구간이다.

프롤로그 완료와 CH01 진입은 별도 진행 단계로 처리한다.

CH01 진입 성공 시 NPC 10명 전체가 공개된다.

CH02, CH03, CH04 및 분기 재방문에서도
공개된 NPC 목록을 유지한다.

NPC 공개와 개별 NPC의 비공개 진술 공개는
서로 다른 권한 정책이다.

NPC가 공개되었다는 이유로 모든 증거와 진술을
열람할 수 있다고 판단해서는 안 된다.

챕터 전환 이후 다음 데이터를 다시 조회한다.

- 게임 상태
- 공개 NPC 및 현재 선택 상태
- 장소 접근 권한
- 획득 증거
- 수사 목표
- 미확인 스토리 이벤트

기존 저장 세션의 NPC 목록 보정은
성공적인 챕터 전환 시 적용된다.

모든 기존 세션에 대한 별도 일괄 마이그레이션은 수행하지 않았다.

## 7. 수사 목표

    GET /api/games/{sessionId}/objectives

목표별 응답 필드:

- objectiveId
- chapter
- title
- description
- status

서버에서 공개된 목표만 표시한다.

완료 여부를 프론트엔드에서 별도로 판정하지 않는다.

이전 챕터에서 공개된 목표도 반환될 수 있으므로
chapter 및 status를 기준으로 화면을 구분한다.

목표 문구와 세부 상태는 05-objective-display-text.md를 참고한다.

## 8. NPC 대화 및 증거 제시

### 8.1 현재 사용 가능한 계약

    POST /api/games/{sessionId}/chat

일반 대화:

    {
      "question": "질문 내용"
    }

단일 증거 제시:

    {
      "question": "이 자료에 대해 설명해 주세요.",
      "presentedEvidenceId": "<획득한 증거 ID>"
    }

현재 question은 필수이다.

현재 dev 구현에서는 evidenceIds 및 note를
신규 요청 필드로 전송하지 않는다.

### 8.2 복수 증거 제시 예정 계약

    {
      "question": "두 자료를 비교해 주세요.",
      "evidenceIds": ["<증거 ID 1>", "<증거 ID 2>"],
      "note": "플레이어가 발견한 관련성"
    }

예정 정책:

- evidenceIds는 1~2개
- 동일 증거 중복 금지
- presentedEvidenceId 기존 지원 유지
- 두 증거 필드 동시 사용 금지
- note는 선택 입력이며 최대 200자
- 한 요청에 NPC 응답 한 번
- 권한 또는 상태 검증 실패 시 전체 처리 중단
- 미수집 증거 및 보호 증거 정책 유지

구현 예정일: 2026-11-29.

현재는 계약 문서만 확정된 상태이므로
프론트엔드 복수 증거 제출 제한을 유지한다.

상세 내용은 07-multi-evidence-chat-contract.md를 참고한다.

## 9. 힌트 API

    POST /api/games/{sessionId}/agents/hint

요청:

    {
      "level": 1,
      "expectedRevision": 12
    }

level은 1~3이다.

응답의 주요 필드:

- agentType
- text
- sourceIds
- level
- status
- chapter
- collectedCount
- suggestedCharacterId
- revision

힌트 API는 읽기 전용이며
게임 진행 상태를 변경하지 않는다.

현재 구현에는 별도 힌트 사용 횟수 차감이나
사용 제한 정책이 확인되지 않았다.

힌트 출처는 서버에서 접근 가능한 자료만 반환한다.

## 10. 알림 및 스토리 이벤트

GameResponse.events는 영구적인 알림 목록이 아니다.

응답에 포함될 수 있는 진행 이벤트:

- CHAPTER_CHANGED
- NPC_UNLOCKED
- EVIDENCE_COLLECTED
- EVIDENCE_PRESENTED
- NPC_REPLIED
- KNOWLEDGE_UPDATED
- GAME_PROGRESS_UPDATED
- ACCUSATION_RESULT

이벤트는 해당 API 처리 결과에 따라 반환된다.

모든 응답이 모든 이벤트를 제공하는 것은 아니다.

현장 조사 API는 created 및 evidenceId를 사용하여
신규 획득을 판별할 수 있다.

스토리 이벤트의 미확인 상태는 별도 API로 조회한다.

    GET /api/games/{sessionId}/story-events/pending

상세 조회:

    GET /api/games/{sessionId}/story-events/{eventKey}

사용자가 확인한 후:

    POST /api/games/{sessionId}/story-events/{eventKey}/ack

ACK 응답에는 확인 결과와 revision이 포함된다.

이벤트 확인 이후 최신 게임 상태와 대기 목록을 다시 조회한다.

## 11. 세션 복원

브라우저 새로고침 또는 재접속 시 다음 순서로 조회한다.

1. GET /api/games/{sessionId}
2. GET /api/games/{sessionId}/evidence
3. GET /api/games/{sessionId}/locations
4. GET /api/games/{sessionId}/objectives
5. GET /api/games/{sessionId}/story-events/pending
6. 필요한 NPC 대화 이력 조회

현재 서버 상태와 수집 증거를 기준으로 화면을 복원한다.

프론트엔드 캐시만으로 수사 진행 상태를 복원하지 않는다.

Day 9 테스트에서는 새 FastAPI 인스턴스와 동일 SQLite를
이용하여 주요 영속 상태 및 이벤트 복원을 검증하였다.

실제 브라우저 및 전체 NPC 대화 이력의 복원 검증은
별도 통합 테스트가 필요하다.

## 12. 보호 콘텐츠 동의 API

신규 주소:

    POST /api/games/{sessionId}/consent

요청:

    {
      "expectedRevision": 12,
      "consent": true
    }

응답은 기존 GameResponse를 유지한다.

동의 가능 여부와 동의 상태는
서버가 제공하는 e30ConsentAvailable 및
e30ConsentGranted 값을 기준으로 처리한다.

동의 요청 성공이 보호 증거 획득 또는
심화 엔딩 활성화를 의미하지 않는다.

기존 증거 ID가 포함된 동의 API도 하위 호환성을 유지한다.

프론트엔드 소스에는 보호 증거 번호를
새롭게 하드코딩하지 않는다.

## 13. 최종 재구성 및 범인 지목

### 13.1 최종 재구성

    POST /api/games/{sessionId}/reconstruction

요청 필드:

- expectedRevision
- selections

selections 항목:

- motive: 동기
- access: 접근
- timeline: 시간
- coverup: 은폐

기존 판정 엔진 기준으로 항목별 2~3개의 증거가 필요하다.

3~4개 항목을 제출하고 최소 3개의 독립적인
정답 조합을 충족해야 한다.

응답 필드:

- accepted
- created
- revision

실제 승인 조합과 선행 조건은 정본 확정이 필요하다.

프론트엔드는 정답 조합을 자체 코드에 포함하지 않는다.

### 13.2 범인 지목

    POST /api/games/{sessionId}/accusations

요청 필드:

- suspectId
- expectedRevision

지목 가능 여부는 GameResponse.canAccuse를 사용한다.

확장판은 수집 개수와 수집 점수의 50% 조건을
모두 검사한다.

기존 지목 기회 3회 제한을 유지한다.

주요 결과:

- CORRECT
- INCORRECT
- NOT_ENOUGH_EVIDENCE

프론트엔드는 result 및 game 응답에 따라 화면을 전환한다.

### 13.3 현재 활성화 상태

#230에서 판정 원장 로더 및 실제 FastAPI 초기화 연결을 구현했다.

그러나 기존 v0.15.0에는 원장 승인 계약이 없다.

따라서 현재 실제 정본 기준 최종 재구성 및
원장이 필요한 지목 요청은 활성화되지 않은 상태이다.

HTTP 503을 게임 내 추리 실패로 표시하지 않는다.

실제 판정 활성화는 Day 10 신규 P0 이슈에서 진행한다.

## 14. 엔딩 API

    GET /api/games/{sessionId}/ending

백엔드 엔딩 코드:

| 코드 | 의미 |
|---|---|
| NO_EVIDENCE | 증거 부족 |
| UNSOLVED | 사건 미해결 |
| ESTIMATED | 추정 해결 |
| FULL | 완전 해결 |
| DEEP | 심화 해결 |

프론트엔드는 서버의 실제 엔딩 결과를 기준으로 표시한다.

응답의 outcome과 게임 상태 및 기존
endingKey 매핑 계약을 구분한다.

서버에 별도의 endingKey 필드가 구현되었다고
임의로 가정하지 않는다.

사건 정답 상세 정보는 허용된 FULL 및 DEEP
엔딩 조회에서만 제공한다.

엔딩 5종은 테스트용 원장으로 검증하였다.

실제 콘텐츠 기반 FULL 및 DEEP 자연 플레이는
아직 검증되지 않았다.

## 15. 발견 기반 타임라인

예정 주소:

    GET /api/games/{sessionId}/timeline

응답 예정 필드:

- revision
- contradictionMarkingAvailable
- items

항목 예정 필드:

- id
- occurredAt
- timeLabel
- title
- description
- chapterId
- sourceIds
- discoveryOrder
- discoveredRevision
- isContradiction

정책:

- 발견하고 공개 승인된 항목만 표시
- 미발견 항목 및 관리자 전용 원장 미공개
- 발견 순서와 사건 시각을 구분
- 알 수 없는 기존 발견 시점은 null 처리
- 사용자 수동 모순 표시와 서버 검증 결과 구분
- 읽기 전용 조회

구현 예정일: 2026-11-30.

현재는 실제 API가 구현되지 않았다.

상세 계약은 08-timeline-api-contract.md를 참고한다.

## 16. 실제 서버 실행 환경

| 서비스 | 포트 |
|---|---:|
| FastAPI | 8000 |
| 확장판 Django | 18004 |
| Qdrant | 6333 |
| Neo4j HTTP | 7474 |
| Neo4j Bolt | 7687 |
| Ollama | 11434 |

기준 콘텐츠 릴리스:

    v0.15.0

기준 RAG 컬렉션:

    case001_rag_1120_revision2

필요한 외부 서비스 및 비공개 콘텐츠 환경을 준비한 후
backend 디렉터리에서 실행한다.

    $env:CRIMESCENE_EXPANDED_RELEASE_VERSION = "v0.15.0"
    $env:CRIMESCENE_REQUIRE_EXPANDED_TRUTH = "false"

    & .\.venv\Scripts\python.exe -m uvicorn crimescene.api.expanded_main:app --host 127.0.0.1 --port 8000

현재 v0.15.0은 원장 미승인 상태이므로
제한된 개발 모드로 실행해야 한다.

정식 배포 검증에서는 원장 승인을 완료하고
CRIMESCENE_REQUIRE_EXPANDED_TRUTH=true를 적용한다.

## 17. 프론트엔드 우선 확인 사항

- 신규 동의 주소 사용
- 장소 및 Action 서버 접근 상태 반영
- CH01 진입 시 NPC 10명 표시
- 챕터 전환 이후 상태 재조회
- 수사 목표 제목 및 설명 표시
- 힌트 단계별 응답 처리
- 스토리 이벤트 대기 목록 및 ACK
- 새로고침 이후 게임 상태 복원
- Revision 충돌 처리
- 복수 증거 제시 구현 전 제한 유지
- 타임라인 구현 전 실제 API 호출 제한
- 최종 판정 미승인 상태에 대한 안내

## 18. 남은 검증 범위

본 문서는 Day 9의 코드 및 자동화 테스트 기준 통합 명세이다.

실제 프론트엔드 브라우저 연동,
모든 콘텐츠 승인,
자연 플레이 전체 엔딩,
정식 운영 배포는 별도 검증이 필요하다.
