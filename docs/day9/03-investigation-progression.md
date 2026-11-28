# Day 9 - 현장 조사 및 챕터 진행 통합 검증

## 1. 작업 개요

| 항목 | 내용 |
|---|---|
| 프로젝트 | 마지막 기록: 졸업하지 못한 밤 |
| 사건 코드 | CASE-001 |
| 작업 일자 | 2026-11-28 |
| GitHub 이슈 | #212 |
| 기준 브랜치 | dev |
| 작업 브랜치 | test/212-investigation-progression |
| 콘텐츠 버전 | case001_1120 |
| 선행 이슈 | #211 |

## 2. 작업 배경

기존 백엔드에는 현장 조사, 증거 수집, 챕터 전환,
NPC 접근 권한 및 세션 복원 기능이 각각 구현되어 있다.

그러나 개별 기능의 정상 동작만으로는 프론트엔드에서
실제 게임 진행 순서에 따라 모든 API가 정상적으로
연동되는지 보장할 수 없다.

기존 테스트에서는 일부 선행 증거 및 챕터 상태를
테스트 데이터로 직접 구성하였다.

이번 작업에서는 게임 생성부터 실제 HTTP 요청을
통해 초기 증거 획득과 양방향 조사 분기 진행을
검증하는 통합 테스트를 추가하였다.

## 3. 작업 목적

- 게임 세션 생성 및 프롤로그 완료 검증
- CH01 초기 조사 증거 획득 검증
- CH02 및 CH03 양방향 분기 진행 검증
- 챕터별 장소 및 조사 Action 활성화 검증
- 선행 조건 미충족 시 상태 변경 방지
- 중복 증거 및 점수 지급 방지
- 이전 Revision 요청 차단
- NPC 선택 권한 검증
- 세션 복원 및 상태 일관성 검증
- 콘텐츠 승인 실패 시 증거 획득 차단

## 4. 기존 테스트 분석

| 테스트 파일 | 기존 검증 범위 |
|---|---|
| test_investigation_http.py | 현장 조사 및 장소 권한 |
| test_chapter_api.py | 챕터 전환 및 보안 |
| test_versioned_chapter_api.py | 확장판 챕터 분기 |
| test_expanded_chapter_runtime.py | 확장판 챕터 해금 정책 |
| test_issue28_npc_unlock.py | NPC 해금 엔진 |
| test_issue28_real_progression.py | 기존 콘텐츠 증거 및 NPC 진행 |

신규 테스트에서는 게임 상태와 획득 증거를
직접 삽입하지 않고 실제 HTTP 요청으로 진행한다.

## 5. 테스트 환경

| 항목 | 구성 |
|---|---|
| 운영체제 | Windows |
| Python | 3.13.15 |
| pytest | 9.2.0 |
| pluggy | 1.7.0 |
| FastAPI | 실제 애플리케이션 사용 |
| HTTP 요청 | FastAPI TestClient |
| 데이터베이스 | 독립 SQLite 임시 저장소 |
| Django 승인 서비스 | httpx.MockTransport |
| 챕터 규칙 | build_expanded_chapter_rules |
| 조사 규칙 | ACTION_CANDIDATES |
| 증거 획득 정책 | proposed_routes |
| 증거 점수 | PROPOSED_SCORES |

Django 승인 응답과 증거 카탈로그는 테스트 환경에서
구성한다.

실제 배포용 콘텐츠 Manifest의 승인 상태를
검증한 결과는 아니다.

Qdrant, Ollama, Neo4j 및 실제 NPC 대화 엔진은
이번 신규 테스트 범위에 포함하지 않는다.

## 6. 통합 테스트 진행 구조

    CH00 게임 생성
          |
          v
    프롤로그 완료
          |
          v
    CH01 진입
          |
          v
    E11 / E19 / E20 획득
          |
          +-----------------------+
          |                       |
          v                       v
        CH02                    CH03
          |                       |
          v                       v
    E12 / E13 / E14      E21 / E23 / E25
          |                       |
          +-----------------------+
                      |
                      v
            조사 분기 재방문
                      |
                      v
            게임 상태 및 세션 검증

두 조사 분기의 진입 순서를 각각 검증한다.

- CH01 -> CH02 -> CH03
- CH01 -> CH03 -> CH02

## 7. 챕터별 증거 획득 결과

| 챕터 | Action ID | 증거 | 점수 |
|---|---|---|---:|
| CH01 | inspect-e11-a | E11 | 1 |
| CH01 | inspect-e19-a | E19 | 1 |
| CH01 | inspect-e20-a | E20 | 2 |
| CH02 | inspect-e12-a | E12 | 1 |
| CH02 | inspect-e13-a | E13 | 2 |
| CH02 | inspect-e14-a | E14 | 3 |
| CH03 | inspect-e21-a | E21 | 2 |
| CH03 | inspect-sensor-record | E23 | 3 |
| CH03 | inspect-emergency-door-record | E25 | 2 |
| 합계 | 9개 | 9개 | 17 |

### 7.1 챕터별 누적 점수

| 진행 단계 | CH02 우선 | CH03 우선 |
|---|---:|---:|
| 게임 생성 | 0 | 0 |
| CH01 조사 완료 | 4 | 4 |
| 첫 번째 분기 조사 완료 | 10 | 11 |
| 두 번째 분기 조사 완료 | 17 | 17 |
| 분기 재방문 | 17 | 17 |

두 분기 진행 순서와 관계없이 동일한 증거 9개와
최종 점수 17점을 유지한다.

분기 재방문 시 점수 및 획득 증거는 변경되지 않는다.

## 8. 장소 조회 API 통합 검증

    GET /api/games/{session_id}/locations

다음 항목을 검증하였다.

- 현재 챕터와 응답의 currentChapter 일치
- SQLite 상태와 응답의 Revision 일치
- 현재 챕터의 접근 가능한 조사 Action 활성화
- 다른 챕터의 Action 비활성화
- 선행 증거 획득 이후 조사 Action 활성화
- 조회 요청으로 인한 상태 변경 방지

## 9. 챕터 전환 API 통합 검증

    POST /api/games/{session_id}/chapter/advance

검증 항목:

- 프롤로그 완료 이후 CH01 진입
- 초기 선행 증거 미충족 시 분기 진입 차단
- CH02 및 CH03 양방향 진입
- 해금된 조사 분기 재방문
- CHAPTER_CHANGED 이벤트 확인
- 기존 획득 증거 및 점수 유지
- 최종 챕터 조건 미충족 시 CH04 진입 차단

## 10. 증거 획득 및 상태 일관성

    POST /api/games/{session_id}/investigations/{action_id}

신규 증거 획득 시 다음 조건을 검증한다.

- 응답의 evidenceId 일치
- created 값이 true
- 획득 증거 목록에 신규 증거 추가
- 증거별 점수 정확히 반영
- Revision 1회 증가
- SQLite 상태와 API 응답 일치
- NPC 선택 정보의 Revision 동기화

동일한 증거를 반복 조사하면 created 값은 false이며
점수 및 Revision이 증가하지 않아야 한다.

이전 Revision을 사용한 요청은 HTTP 409로 차단한다.

## 11. 세션 복원 검증

검증 대상 API:

    GET /api/games/{session_id}
    GET /api/games/{session_id}/evidence
    GET /api/games/{session_id}/locations

기존 소유권 쿠키를 유지한 새로운 HTTP 클라이언트에서
게임 상태를 복원하였다.

검증 결과:

- 세션 ID 유지
- 현재 챕터 유지
- 획득 증거 유지
- 수집 점수 유지
- Revision 유지
- 장소 접근 정보 조회 성공
- 조회 과정에서 저장 상태 변경 없음

실제 서버 프로세스를 종료하고 다시 실행하는
재시작 복구 테스트는 이번 검증에 포함하지 않는다.

## 12. NPC 접근 권한 검증

    POST /api/games/{session_id}/characters/{character_id}/select

| 검증 항목 | 결과 |
|---|---|
| 초기 NPC C01 확인 | 통과 |
| 미해금 C02 선택 | HTTP 403 |
| 해금된 C01 선택 | HTTP 200 |
| 선택 상태와 GameState 일치 | 통과 |
| 미해금 NPC 선택 실패 시 상태 보존 | 통과 |

이 테스트는 현재 NPC 선택 권한을 검증한다.

확장판 NPC 신규 해금 기능의 완성 또는 정상 동작을
의미하지 않는다.

## 13. 발견된 NPC 해금 정책 문제

### 13.1 현상

현재 확장판에서는 기존 콘텐츠의 NPC 해금 정책을
의도적으로 사용하지 않는다.

expanded_main.py의 런타임 초기화 과정에서
dialogue_flag_config를 None으로 설정한다.

현장 조사 API에서는 증거 획득과 점수 반영은
수행하지만 NPC 신규 해금 평가가 연결되지 않았다.

### 13.2 스토리 원본 검토

04_SCENES.json의 전체 30개 장면을 검토하였다.

SC-0101의 초기 NPC 공개 범위는 담당자 확인이
필요한 제안 상태로 남아 있다.

해당 장면에는 공개 NPC 최소 3명 조사 조건이
제안되어 있다.

현재 백엔드 초기 상태에서는 C01만 해금된다.

### 13.3 영향 범위

| 대상 | 관련 NPC | 영향 |
|---|---|---|
| E12 대체 경로 | C07 | NPC 기반 획득 제한 |
| E14 대체 경로 | C08 | NPC 기반 획득 제한 |
| E15 | C05 | 증거 획득 차단 위험 |
| E16 | C09 | 증거 획득 차단 위험 |
| E22 해당 경로 | C04 | NPC 기반 획득 제한 |
| E28 | C06 | 최종 챕터 진입 차단 위험 |

E28은 CH04 진입에 필요한 필수 증거이므로
NPC 해금 정책 문제는 정식 배포 전 해결해야 한다.

### 13.4 처리 방향

우선순위: P0

- 스토리 담당자와 초기 NPC 공개 범위 확정
- 챕터별 추가 NPC 해금 조건 확정
- 증거 기반 NPC 해금 조건 확정
- 확장판 전용 정책 구현
- 현장 조사 및 대화 API 연동
- 챕터 이동 시 해금 정책 평가
- 기존 NPC 해금 상태 유지
- NPC_UNLOCKED 이벤트 연동
- 보호 콘텐츠 접근 정책 유지

현재 이슈에서는 승인되지 않은 NPC 해금 정책을
임의로 추가하지 않았다.

별도 버그 이슈로 추적하며 정식 배포 완료 전에
해결해야 한다.

## 14. 보안 및 상태 무결성 검토

| 검토 항목 | 결과 |
|---|---|
| 선행 증거 미충족 | 조사 차단 |
| 다른 챕터 Action | 조사 차단 |
| 미해금 NPC 선택 | 접근 차단 |
| 이전 Revision | HTTP 409 |
| 중복 증거 획득 | 점수 증가 없음 |
| 콘텐츠 승인 실패 | 증거 획득 차단 |
| 실패 요청의 상태 변경 | 없음 |
| 조회 요청의 상태 변경 | 없음 |
| 챕터 재방문 | 증거 및 점수 유지 |
| API 및 SQLite 상태 일치 | 검증 통과 |

## 15. 신규 테스트 구성

| 테스트 | 검증 내용 |
|---|---|
| test_day9_investigation_branch_flow | 양방향 조사 분기 2건 |
| test_day9_investigation_prerequisite_rollback | 선행 조건 및 상태 보존 |
| test_day9_investigation_duplicate_and_stale | 중복 및 이전 Revision |
| test_day9_investigation_session_restore | 세션 복원 |
| test_day9_investigation_npc_access | NPC 선택 권한 |
| test_day9_investigation_approval_failure | 콘텐츠 승인 실패 |

테스트 함수 6개이며 파라미터 테스트를 포함하여
총 7개 테스트 케이스를 실행하였다.

## 16. 테스트 결과

| 테스트 범위 | 통과 | 실패 | 제외 | 실행 시간 |
|---|---:|---:|---:|---:|
| 신규 통합 테스트 | 7 | 0 | 0 | 3.70초 |
| 전체 백엔드 회귀 테스트 | 3181 | 0 | 26 | 144.48초 |

### 16.1 이전 작업 대비 결과

| 작업 | 전체 통과 건수 | 증가 |
|---|---:|---:|
| #210 | 3161 | - |
| #211 | 3174 | 13 |
| #212 | 3181 | 7 |

### 16.2 제외 테스트

| 제외 사유 | 건수 |
|---|---:|
| 실제 외부 서비스 통합 환경 필요 | 14 |
| Windows 심볼릭 링크 사용 불가 | 1 |
| 비공개 엔딩 이미지 선택 실행 | 2 |
| 별도 Neo4j 테스트 환경 필요 | 6 |
| 실제 Ollama 선택 실행 | 3 |
| 합계 | 26 |

## 17. 프론트엔드 연동 지침

현장 조사 성공 이후 다음 순서로 화면을 갱신한다.

1. 조사 POST API 응답을 확인한다.
2. 최신 Revision과 점수를 확인한다.
3. GET /api/games/{session_id}를 호출한다.
4. GET /api/games/{session_id}/evidence를 호출한다.
5. GET /api/games/{session_id}/locations를 호출한다.
6. 최신 NPC 목록과 조사 버튼 활성화 상태를 반영한다.

현재 현장 조사 API의 응답에는 GameResponse 전체가
포함되지 않으므로 게임 상태 API를 별도로 조회한다.

NPC 목록은 서버의 unlockedCharacters를 기준으로
처리하며 프론트엔드에서 임의로 해금하지 않는다.

## 18. 변경 파일

- backend/tests/test_day9_investigation_progression.py
- docs/day9/03-investigation-progression.md

이번 이슈에서는 운영 백엔드 코드, 프론트엔드 코드,
데이터베이스 구조 및 콘텐츠 원본을 수정하지 않았다.

## 19. 제한사항 및 후속 작업

- 실제 Django 승인 서버 연동은 검증하지 않았다.
- 테스트용 증거 카탈로그와 승인 응답을 사용하였다.
- 정식 콘텐츠 Manifest의 전체 획득 경로를 검증하지 않았다.
- 실제 NPC 신규 해금 정책은 미확정 상태이다.
- NPC 대화 기반 증거 획득은 이번 범위에 포함하지 않았다.
- CH04 정상 진입 및 엔딩 완료는 후속 검증 대상이다.
- 실제 서버 재시작 이후 복구는 별도 검증이 필요하다.
- 프론트엔드 실서버 연동은 별도로 검증해야 한다.

## 20. 최종 결과

실제 FastAPI HTTP 요청과 독립 SQLite 저장소를
사용하여 현장 조사 및 챕터 진행을 통합 검증하였다.

두 가지 조사 분기 순서에서 증거 9개와 점수 17점을
동일하게 획득하는 것을 확인하였다.

신규 통합 테스트 7건 및 전체 백엔드 회귀 테스트
3181건이 통과하였다.

확장판 NPC 해금 정책 누락 위험을 발견하였으며
정식 배포 전 해결해야 할 P0 문제로 분리하였다.

전체 게임의 자연 플레이 완료를 검증한 것은 아니며,
NPC 해금 문제 해결 이후 최종 챕터와 엔딩까지
연결되는 통합 검증이 추가로 필요하다.
