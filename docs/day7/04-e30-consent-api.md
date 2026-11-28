# Day 7 - E30 Consent API and Independent Approval Gate

## 1. Overview

Issue #192는 보호 증거 E30의 명시적 플레이어 동의 API와
독립 콘텐츠 승인 게이트를 구현한다.

기존 게임 진행 상태, Django 콘텐츠 승인 정책,
릴리스 무결성 및 SQLite 트랜잭션을 유지한다.

본 단계는 동의 기반 구현이며 실제 E30 콘텐츠 공개는
후속 승인 및 스토리 계약 확정 이후 진행한다.

## 2. E30 Contract

| Item | Value |
|---|---|
| Evidence ID | E30 |
| Character | C08 |
| Chapter | CH04 |
| Scene | SC-0405 |
| Story Event | STORY_030 |
| Required Evidence | E14, E16, E18 |
| Evidence Score | 3 |
| Runtime Publication | Disabled |

## 3. System Architecture

    React Frontend
        |
        v
    FastAPI GameState Validation
        |
        v
    E30 Consent Service
        |
        v
    DjangoContentClient
        |
        v
    Django Service Token Validation
        |
        v
    Immutable Base Release Validation
        |
        v
    Independent E30 Review Validation
        |
        v
    Evidence / Scene Approval Validation
        |
        v
    Player Consent
        |
        v
    SQLite Atomic Commit

## 4. GameResponse Extension

기존 응답 필드를 삭제하거나 변경하지 않는다.

| Field | Type | Default |
|---|---|---|
| e30ConsentAvailable | boolean | false |
| e30ConsentGranted | boolean | false |

e30ConsentAvailable은 현재 동의 요청 가능 여부이다.

e30ConsentGranted는 저장된 플레이어 동의 기록이다.
콘텐츠 승인이나 당사자 안전 검증 완료를 의미하지 않는다.

## 5. Player Consent API

Method:

    POST

Endpoint:

    /api/games/{session_id}/evidence/E30/consent

Request:

    {
      "expectedRevision": 42,
      "consent": true
    }

Response:

    HTTP 200
    GameResponse

정상적인 신규 동의 요청은 revision을 1 증가시킨다.

현재 revision을 사용하는 중복 동의 요청은
승인 및 진행 조건이 유지되는 경우 상태를 변경하지 않는다.

## 6. HTTP Status Codes

| Status | Description |
|---|---|
| 200 | 동의 저장 또는 멱등 처리 |
| 404 | 세션 소유권 검증 실패 |
| 409 | 동의 불가 또는 Revision 충돌 |
| 422 | 요청 형식 오류 또는 명시적 동의 누락 |

## 7. Consent Preconditions

- CASE-001
- case001_1120
- INVESTIGATION 상태
- 종료되지 않은 게임
- CH04 진입 및 해금
- E14, E16, E18 획득
- E30 미획득
- 별도 Django 승인 계약 충족

## 8. State Management

GameState 신규 필드:

    e30_player_consent: bool = False

플레이어 동의는 다음 상태를 변경하지 않는다.

- evidence
- score
- flags
- document_grants
- queued_story_events
- attempts_left
- ending_code

기존 SQLite 저장 데이터는 기본값 false로 호환한다.

## 9. Django Independent Review API

Method:

    GET

Endpoint:

    /api/content/internal/cases/{case_id}/releases/{version}/e30-consent-reviews/{review_version}/

기존 HasContentServiceToken 권한을 재사용한다.

프론트엔드에서는 해당 내부 API를 직접 호출하지 않는다.

검증 항목:

- 기존 불변 ContentRelease
- 기존 릴리스 SHA-256
- 별도 검토 릴리스 SHA-256
- E30_CONSENT_REVIEW Scope
- 기존 릴리스와 검토 릴리스 분리
- E30 및 SC-0405 승인 상태
- 콘텐츠 버전
- SC-0405 챕터와 공개 범위
- E30 점수 및 선행 증거
- 실제 증거 및 Scene 내용의 SHA-256

정상 응답은 승인 메타데이터만 포함한다.
서면 진술 원문은 반환하지 않는다.

## 10. Runtime Configuration

Existing:

    CRIMESCENE_EXPANDED_RELEASE_VERSION=v0.15.0

New:

    CRIMESCENE_E30_CONSENT_REVIEW_VERSION

신규 환경변수는 기본적으로 설정하지 않는다.

별도 검토 버전이 없거나 승인 조회에 실패하면
동의 가능 상태는 false가 된다.

기존 v0.15.0 Manifest는 수정하지 않는다.

## 11. Security Policy

- 기존 게임 세션 소유권 검증 재사용
- 엄격한 Pydantic 요청 타입 검증
- 예상 Revision 검증
- SQLite 원자적 상태 변경
- 중복 동의에 따른 상태 변경 방지
- 승인 서비스 장애 시 Fail-closed 처리
- 클라이언트 임의 승인 정보 입력 차단
- 기존 E30 일반 수집 경로 차단 유지
- 기존 E30 상세 및 이미지 접근 차단 유지
- STORY_030 일반 이벤트 전달 차단 유지
- 동의만으로 E30 또는 보호 플래그를 지급하지 않음
- 동의 API 정상 응답에 private, no-store 적용

## 12. Test Results

| Suite | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|
| FastAPI Focused Integration | 125 | 0 | 3 | 5.90s |
| Django E30 Review | 19 | 0 | 0 | 0.044s |
| FastAPI Full Regression | 2658 | 0 | 26 | 69.96s |
| Django Full Regression | 247 | 0 | 0 | 12.513s |

Full Regression Summary:

| Metric | Result |
|---|---:|
| Passed | 2905 |
| Failed | 0 |
| Skipped | 26 |

부분 테스트와 전체 회귀 테스트는 중복되므로 합산하지 않는다.

Issue #192 신규 테스트:

| Category | Count |
|---|---:|
| FastAPI Consent API | 11 |
| FastAPI Approval Client | 19 |
| Django Approval View | 19 |
| Total | 49 |

## 13. Skipped Tests

| Reason | Count |
|---|---:|
| Day 6 External Services | 14 |
| Windows Symbolic Link | 1 |
| Private Ending Image Opt-in | 2 |
| Neo4j Integration | 6 |
| Ollama Integration | 3 |
| Total | 26 |

## 14. Frontend Integration

1. 기존 GameResponse에서 e30ConsentAvailable을 확인한다.
2. true인 경우 동의 UI를 표시한다.
3. 플레이어가 명시적으로 동의하면 consent API를 호출한다.
4. 응답 GameResponse로 최신 상태를 반영한다.
5. e30ConsentGranted로 플레이어 동의 기록을 확인한다.
6. HTTP 409 발생 시 최신 게임 상태를 다시 조회한다.

교차 출처 요청에서는 기존 세션 쿠키를 전달한다.

동의 완료만으로 E30 획득 UI 또는 DEEP 엔딩을
활성화하지 않는다.

## 15. Limitations and Follow-up

실제 콘텐츠 승인 및 E30 공개는 활성화하지 않았다.

Django 승인 View 테스트는 모의 ORM 기반이다.
실제 서비스 토큰 인증 및 DB 기반 승인 HTTP 통합 테스트는
별도로 수행해야 한다.

다음 기능은 후속 작업으로 분리한다.

- 9-B DEEP 엔딩 최종 스토리 계약 확정
- 스토리상 당사자 동의 및 안전 판정
- 독립 검토 릴리스의 실제 승인 및 생성
- SC-0405 서면 진술 공개
- STORY_030 전용 전달 게이트
- consent_and_safety_verified 서버 검증
- E30 획득 및 3점 원자적 지급
- 실제 DEEP 엔딩 도달 테스트

실제 활성화 이전에는 일반 Django 콘텐츠 조회 경로의
E30 우회 공개 여부를 추가 검증한다.

저장된 플레이어 동의와 현재 승인 버전의 일치 여부도
실제 콘텐츠 공개 시 재검증해야 한다.

## 16. Conclusion

플레이어 동의 API 및 독립 콘텐츠 승인 기반을 구현했다.

기존 콘텐츠 보호 정책을 유지하며,
FastAPI 및 Django 전체 회귀 테스트를 통과했다.

---

## 이슈 #210 - 동의 API 별칭

- 작업 일자: 2026-11-28
- 작업 브랜치: feature/210-consent-api-alias

### 신규 권장 API

    POST /api/games/{session_id}/consent

### 기존 API

    POST /api/games/{session_id}/evidence/E30/consent

두 API는 동일한 동의 처리 함수와 GameResponse 응답 구조를 사용한다.

### 요청 형식

    {
      "expectedRevision": 12,
      "consent": true
    }

### 변경 사항

- 증거 ID가 포함되지 않는 동의 API 경로 추가
- 기존 API 하위 호환성 유지
- 기존 요청 및 응답 형식 유지
- 기존 Django 콘텐츠 승인 정책 유지
- 신규 및 기존 API 간 교차 호출 멱등성 유지
- 프론트엔드 스포일러 검사 충돌 해결

### 테스트 결과

- 동의 API 초기 검증: 22건 통과
- 관련 기능 통합 테스트: 129건 통과, 3건 제외
- 전체 백엔드 회귀 테스트: 3161건 통과, 26건 제외
- 테스트 실패: 0건

상세 작업 내용은 docs/day9/01-consent-api-alias.md를 참고한다.

실제 콘텐츠 승인 서버 및 프론트엔드 실서버 연동 검증은
별도로 진행한다.
