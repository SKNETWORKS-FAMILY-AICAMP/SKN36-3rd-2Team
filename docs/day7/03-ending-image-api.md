# Day 7 - Protected Ending Image API

## 1. Overview

Issue #191은 엔딩 이미지의 사전 열람과 비인가 접근을
방지하기 위한 보호 API를 제공한다.

기존 FastAPI 세션 소유권 검증을 재사용하며,
서버가 확정한 엔딩 코드에 해당하는 이미지만 반환한다.

## 2. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/games/{session_id}/ending/images | 이미지 목록 조회 |
| GET | /api/games/{session_id}/ending/images/{image_index} | 이미지 조회 |
| GET | /api/games/{session_id}/ending | 기존 엔딩 조회 |

기존 엔딩 API의 응답 계약은 변경하지 않는다.

## 3. Ending Image Mapping

| Ending Code | Index | Image |
|---|---:|---|
| NO_EVIDENCE | - | None |
| UNSOLVED | 1 | escaped.png |
| ESTIMATED | - | None |
| FULL | - | None |
| DEEP | 1 | deep_album_blank.png |
| DEEP | 2 | deep_album_filled.png |

이미지 번호는 1부터 시작한다.

DEEP 이미지 표시 순서는 프론트엔드에서 관리한다.
서버에서 순차 열람을 강제하지 않는다.

## 4. Response Example

### GET /api/games/{session_id}/ending/images

    {
      "endingCode": "DEEP",
      "images": [
        {
          "index": 1,
          "url": "/api/games/{session_id}/ending/images/1"
        },
        {
          "index": 2,
          "url": "/api/games/{session_id}/ending/images/2"
        }
      ]
    }

이미지가 없는 엔딩은 빈 images 배열을 반환한다.

### GET /api/games/{session_id}/ending/images/1

Response Headers:

    Content-Type: image/png
    Cache-Control: private, no-store
    X-Content-Type-Options: nosniff

## 5. System Architecture

    Frontend
        |
        v
    FastAPI Ending Image Endpoint
        |
        v
    Session Ownership Validation
        |
        v
    GameState / Content Version Validation
        |
        v
    FINISHED State Validation
        |
        v
    Server Ending Code Mapping
        |
        v
    Private Image Path Validation
        |
        v
    FileResponse

## 6. Access Policy

- 기존 게임별 세션 인증 쿠키 지원
- 기존 case001_owner 인증 쿠키 호환
- 세션 소유권 검증
- CASE-001 및 case001_1120 콘텐츠 버전 검증
- FINISHED 상태 검증
- 서버 확정 ending_code 기반 이미지 선택
- 클라이언트 파일명 및 엔딩 코드 지정 불가
- 이미지 번호 범위 검증
- 디렉터리 외부 파일 접근 방지
- 다른 이미지로 연결되는 심볼릭 링크 차단
- GameState 및 Revision 변경 없음

## 7. HTTP Status Codes

| Status | Description |
|---|---|
| 200 | 정상 조회 |
| 404 | 비인가 세션, 잘못된 이미지 번호 또는 이미지 없음 |
| 409 | 게임 종료 전 접근 |
| 422 | 이미지 번호의 요청 형식 오류 |

## 8. Private Image Storage

Default directory:

    backend/.local/case001_ending_images/

Environment variable:

    CRIMESCENE_ENDING_IMAGE_DIR

Directory structure:

    backend/
      .local/
        case001_ending_images/
          deep_album_blank.png
          deep_album_filled.png
          escaped.png
        case001_photos/
          E16.png
          E19.png
          E24.png

이미지는 공개 정적 파일 디렉터리에 저장하지 않는다.
운영 배포 시 해당 디렉터리의 쓰기 권한도 제한해야 한다.

실제 이미지는 Git 저장소에 포함하지 않는다.

## 9. Evidence Images

E16, E19, E24 이미지는 다음 기존 API를 사용한다.

    GET /api/games/{session_id}/evidence/{evidence_id}/photo

Default directory:

    backend/.local/case001_photos/

Environment variable:

    CRIMESCENE_EVIDENCE_IMAGE_DIR

기존 증거 획득 조건 및 E26/E30 보호 정책을 유지한다.

## 10. Frontend Integration

1. 기존 엔딩 API로 게임 종료 상태를 확인한다.
2. 엔딩 이미지 목록 API를 호출한다.
3. images 배열의 url을 사용하여 이미지를 조회한다.
4. DEEP 엔딩은 배열 순서대로 이미지를 표시한다.
5. 이미지가 없는 엔딩은 기존 UI를 표시한다.

교차 출처 fetch 요청에는 credentials: "include"를 사용한다.

API 서버 주소와 이미지 상대 경로를 올바르게 결합해야 한다.
이미지를 프론트엔드 public 폴더에 복사하지 않는다.

## 11. Test Results

### Ending Image Integration

| Metric | Result |
|---|---:|
| Total | 25 |
| Passed | 24 |
| Skipped | 1 |
| Failed | 0 |
| Duration | 4.58s |

### Backend Regression

| Metric | Result |
|---|---:|
| Total | 2654 |
| Passed | 2628 |
| Skipped | 26 |
| Failed | 0 |
| Duration | 75.55s |

두 테스트 실행 결과에는 중복 테스트가 포함된다.

### Verified Cases

- 기존 5종 엔딩 정상 동작
- 엔딩별 이미지 목록 검증
- 게임 종료 전 접근 차단
- 비인가 및 타 세션 접근 차단
- 클라이언트 엔딩 코드 조작 방지
- 이미지 번호 범위 검증
- 이미지 누락 처리
- 모의 외부 경로 탈출 차단
- 모의 내부 이미지 경로 변경 차단
- 실제 DEEP 이미지 2장 반환
- 실제 UNSOLVED 이미지 1장 반환
- 원본 및 HTTP 응답 SHA-256 일치
- GameState 무결성 유지
- 기존 API 호환성 유지

### Skipped Tests

| Reason | Count |
|---|---:|
| Day 6 Live Service Integration | 14 |
| Windows Symbolic Link Permission | 1 |
| Private Image Integration Opt-in | 2 |
| Neo4j Integration | 6 |
| Ollama Integration | 3 |
| Total | 26 |

실제 비공개 이미지 통합 테스트 2건은
별도 opt-in 실행에서 통과하였다.

## 12. Changed Files

- backend/src/crimescene/api/app.py
- backend/src/crimescene/api/ending_image_service.py
- backend/tests/test_expanded_ending_http.py
- docs/day7/03-ending-image-api.md

## 13. Limitations

Windows 환경에서 실제 심볼릭 링크 생성 테스트는 제외되었다.
대체 경로 검증 테스트 2건은 통과하였다.

실제 이미지 테스트는 별도 opt-in 방식으로 실행하였다.

전체 회귀 테스트에서는 외부 서비스 통합 테스트를 제외하였다.
운영 배포 및 실제 브라우저 연동 검증은 별도 수행한다.

엔딩 이미지 제공은 접근 제어이며, 열람 권한을 획득한
사용자의 이미지 복사나 화면 캡처까지 방지하지는 않는다.

## 14. Conclusion

서버에서 확정한 엔딩 상태를 기반으로 비공개 이미지를 제공한다.

기존 세션 소유권 검증과 게임 진행 규칙을 유지하며,
기존 API에 대한 회귀 테스트를 완료하였다.
