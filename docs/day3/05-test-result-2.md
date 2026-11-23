
# Day 3 — Django–FastAPI 콘텐츠 통합 테스트 결과 보고서

## 1. 테스트 개요

| 항목 | 내용 |
|---|---|
| 관련 이슈 | #121 |
| 기준 구현 커밋 | `be0eeba` |
| 테스트 브랜치 | `test/121-day3-content-integration` |
| 테스트 대상 | Django, DRF, FastAPI, React |
| 테스트 방식 | 단위 테스트, ORM 통합 테스트, API 통합 테스트, 회귀 테스트 |
| 데이터 | 가상 테스트 데이터 |
| 결과 | 실행한 자동화 테스트 모두 통과 |

### 검증 목적

- Django 콘텐츠 모델 및 데이터 Import 안정성 확인
- 서비스 간 인증 및 접근 권한 검증
- FastAPI 콘텐츠 연동 기능 검증
- 미승인 콘텐츠 및 내부 정보 노출 차단
- 네트워크 장애 발생 시 안전한 실패 처리
- 기존 게임 기능 회귀 여부 확인

## 2. 최종 테스트 요약

| 검증 대상 | 결과 | 상태 |
|---|---|---|
| Django System Check | 오류 0개 | PASS |
| Django Migration Check | No changes detected | PASS |
| Django 전체 테스트 | 228 PASS | PASS |
| FastAPI 전체 테스트 | 1,734 PASS / 9 SKIP | PASS |
| React Production Build | 성공 | PASS |
| Spoiler Safety Check | 성공 | PASS |

### 전체 자동화 테스트

- Django 실행 테스트: 228개
- FastAPI 실행 테스트: 1,734개
- FastAPI Skip: 9개
- **실제로 통과한 테스트: 총 1,962개**
- 실패: 0개

Skip 9건은 실행되지 않은 테스트로, PASS 건수에 포함하지 않았습니다.

## 3. 기존 기준선 비교

| 구분 | 이슈 작성 당시 기준선 | Issue #121 착수 시 | 최종 결과 |
|---|---:|---:|---:|
| Django PASS | 62 | 189 | **228** |
| FastAPI PASS | 1,564 | 1,724 | **1,734** |
| FastAPI SKIP | 9 | 9 | 9 |

### 분석

Issue #121 진행 중 Django 테스트 39개, FastAPI 테스트 10개를 추가했습니다.

최종 전체 회귀 테스트에서 실패가 발생하지 않았으므로, 이번에 실행한 테스트 집합에서는 기존 동작의 회귀 오류가 발견되지 않았습니다.

단, 테스트 개수 증가만으로 코드 품질이나 성능이 향상됐다고 판단할 수는 없습니다.

## 4. 신규 테스트 상세

### 4.1 검토 완료 이벤트 Import — 10개

테스트 파일:

`backend/django_service/apps/content/test_issue121_import_reviewed_story_events.py`

| 검증 항목 | 예상 동작 | 결과 |
|---|---|---|
| 잘못된 CSV 헤더 | Import 거부 | PASS |
| 증거 ID 중복 | Import 거부 | PASS |
| 미검토 이벤트 | Import 거부 | PASS |
| 잘못된 선행 증거 | Import 거부 | PASS |
| Dry Run 실행 | DB 변경 없음 | PASS |
| 승인된 검토표 적재 | StoryEvent 생성 | PASS |
| 동일 데이터 재적재 | 중복 생성 없음 | PASS |
| 기존 이벤트 충돌 | 전체 트랜잭션 롤백 | PASS |
| DRAFT가 아닌 사건 | Import 거부 | PASS |
| 존재하지 않는 Scene | Import 거부 | PASS |

### 4.2 V3 StoryEvent Import — 14개

테스트 파일:

`backend/django_service/apps/content/test_issue121_import_story_events_v3.py`

테스트용 데이터 구조:

- Scene 30개
- EvidenceLink 23개
- STORY 매핑 15개
- 가상 증거 E01~E30

| 검증 항목 | 예상 동작 | 결과 |
|---|---|---|
| 미검토 목록 Dry Run | 변경 없이 완료 | PASS |
| 검토 완료 이벤트 Dry Run | 생성 내용만 검증 | PASS |
| 정상 이벤트 적재 | 승인 전 상태로 저장 | PASS |
| 동일 데이터 재적재 | 멱등 처리 | PASS |
| 미검토 선택 이벤트 | Import 거부 | PASS |
| 잘못된 CSV 헤더 | Import 거부 | PASS |
| STORY ID 중복 | Import 거부 | PASS |
| 매핑 개수 누락 | Import 거부 | PASS |
| 증거 매핑 불일치 | Import 거부 | PASS |
| Scene 참조 누락 | Import 거부 | PASS |
| Deep Gate 이벤트 | 별도 승인 필요 | PASS |
| 잘못된 선행 증거 | Import 거부 | PASS |
| 기존 이벤트 충돌 | 전체 롤백 | PASS |
| PUBLISHED 사건 Import | Import 거부 | PASS |

### 4.3 Django DRF API 인증·권한 — 15개

테스트 파일:

`backend/django_service/apps/content/test_issue121_api_integration.py`

| 검증 항목 | 예상 동작 | 결과 |
|---|---|---|
| 내부 API 토큰 누락 | 403 | PASS |
| 잘못된 토큰 | 403 | PASS |
| 관리자 세션으로 내부 API 우회 | 403 | PASS |
| 서버 토큰 미설정 | 403 | PASS |
| 지나치게 긴 토큰 | 403 | PASS |
| 관리자 개요 API 권한 | 관리자만 200 | PASS |
| 승인된 Scene 조회 | 공개 필드만 반환 | PASS |
| ENGINE_ONLY Scene | 404 | PASS |
| 승인된 Evidence 조회 | 허용 필드만 반환 | PASS |
| 미승인 Evidence | 404 | PASS |
| 중복 이벤트 선행 증거 | 404 | PASS |
| 공백 이벤트 제목 | 404 | PASS |
| 다른 Case의 이벤트 요청 | 404 | PASS |
| DRAFT 사건의 플레이어 콘텐츠 | 404 | PASS |
| 콘텐츠 승인 현황 API | 승인 개수 반환 | PASS |

### 4.4 FastAPI 장애 대응 — 10개

테스트 파일:

`backend/tests/test_issue121_django_service_failures.py`

| 검증 항목 | 예상 동작 | 결과 |
|---|---|---|
| Django 응답 타임아웃 | 503 | PASS |
| Django 연결 실패 | 503 | PASS |
| 잘못된 JSON | 503 | PASS |
| 내부 필드 포함 응답 | 503 | PASS |
| 응답 크기 제한 초과 | 503 | PASS |
| Django 인증 실패 | 503 | PASS |
| Django 서버 오류 | 503 | PASS |
| 미승인 이벤트 404 | 외부 콘텐츠 숨김 | PASS |
| 정상 Django HTTP 계약 + ACK | ACK 영구 저장 | PASS |
| 이벤트 목록 조회 중 부분 장애 | 부분 데이터 반환 금지 | PASS |

### 4.5 추가된 테스트 총계

| 분류 | 테스트 수 |
|---|---:|
| Django Import | 24 |
| Django API | 15 |
| FastAPI 장애 대응 | 10 |
| **합계** | **49** |

## 5. 핵심 시나리오 분석

### TC-01. Import 멱등성

**목적:** 동일한 콘텐츠를 두 번 적재해도 중복 행이 생성되지 않는지 확인합니다.

**검증 결과**

1. 첫 번째 Import에서 신규 이벤트를 생성했습니다.
2. 동일 CSV로 두 번째 Import를 실행했습니다.
3. 기존 이벤트를 인식했습니다.
4. StoryEvent 개수가 증가하지 않았습니다.

**결과: PASS**

### TC-02. Import 트랜잭션 롤백

**목적:** 여러 이벤트를 적재하는 도중 충돌이 발생하면 앞선 작업까지 취소되는지 확인합니다.

**검증 결과**

1. 첫 번째 신규 이벤트 적재를 시도했습니다.
2. 두 번째 이벤트에서 기존 데이터 충돌을 발생시켰습니다.
3. Import가 오류로 종료됐습니다.
4. 첫 번째 신규 이벤트도 DB에 남지 않았습니다.
5. 기존 충돌 데이터는 변경되지 않았습니다.

**결과: PASS**

### TC-03. 미승인 콘텐츠 차단

**목적:** 승인되지 않은 StoryEvent 및 Evidence가 플레이어 API로 노출되지 않는지 확인합니다.

**검증 결과**

- 미승인 이벤트: 조회 차단
- 미승인 증거: 조회 차단
- 비공개 Scene: 조회 차단
- 미게시 사건: 플레이어 콘텐츠 조회 차단
- 내부 메타데이터: 응답에 포함되지 않음

**결과: PASS**

### TC-04. 서비스 간 인증

**목적:** Django 내부 API를 인증되지 않은 클라이언트가 호출하지 못하도록 제한합니다.

**검증 결과**

- 서비스 토큰 누락: 403
- 잘못된 서비스 토큰: 403
- 서버 토큰 미설정: 403
- 관리자 세션만으로 내부 API 접근: 403

**결과: PASS**

### TC-05. Django 장애 대응

**목적:** Django 장애가 발생했을 때 FastAPI가 내부 정보나 일부 콘텐츠를 반환하지 않는지 확인합니다.

**검증 결과**

- 연결 실패 및 타임아웃 시 503 반환
- 서비스 내부 오류 문자열 노출 차단
- 여러 이벤트 조회 중 일부가 실패하면 부분 목록 반환 차단
- 실패한 ACK는 GameState에 기록되지 않음

**결과: PASS**

### TC-06. ACK 멱등 처리

**목적:** 사용자가 동일한 이벤트 확인 요청을 여러 번 보내더라도 중복 기록이 생성되지 않도록 합니다.

**검증 결과**

- 최초 ACK: `created=true`
- 중복 ACK: `created=false`
- 중복 요청으로 revision이 증가하지 않음
- 이미 확인한 이벤트는 pending 목록에서 제외

**결과: PASS**

해당 시나리오는 Issue #120에서 작성된 테스트와 이번 회귀 테스트를 통해 확인했습니다.

## 6. 테스트 환경

| 항목 | 설정 |
|---|---|
| OS | Windows 개발 환경 |
| Django | 5.2.19 |
| Django 테스트 프레임워크 | Django TestCase / APITestCase |
| FastAPI 테스트 프레임워크 | pytest |
| HTTP 테스트 | httpx.MockTransport / TestClient |
| Django DB | 격리된 테스트 DB |
| FastAPI 상태 저장 | 테스트용 SQLite |
| 콘텐츠 | 가상 데이터 |
| 실제 정본 데이터 변경 | 없음 |

## 7. 테스트 재현 명령어

### Django 전체

```powershell
cd backend/django_service
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
```

### Django 신규 Import 테스트

```powershell
uv run python manage.py test apps.content.test_issue121_import_reviewed_story_events
uv run python manage.py test apps.content.test_issue121_import_story_events_v3
```

### Django 신규 API 테스트

```powershell
uv run python manage.py test apps.content.test_issue121_api_integration
```

### FastAPI 장애 대응 테스트

```powershell
cd backend
uv run pytest -q tests/test_issue121_django_service_failures.py
```

### FastAPI 전체 회귀

```powershell
uv run pytest -q
```

### React

```powershell
cd frontend
npm run build
npm run spoiler
```

## 8. 검증 범위의 한계

이번에 통과한 테스트는 자동화 테스트입니다.

다음 항목은 별도로 검증해야 합니다.

1. 실제 Django 프로세스와 FastAPI 프로세스 간 네트워크 E2E
2. 실제 승인된 CASE-001 콘텐츠를 이용한 전체 게임 플레이
3. 운영 DB Migration 적용 및 롤백 절차
4. 배포 환경에서의 HTTPS 및 서비스 토큰 설정
5. Multi-Agent 및 MCP 추가 후 전체 회귀

**모의 HTTP 응답이 성공했다고 해서 실제 운영 서비스 간 통신까지 검증된 것은 아닙니다.**

## 9. 최종 결론

Issue #121에서 신규 자동화 테스트 49개를 추가했습니다.

- Django 228 PASS
- FastAPI 1,734 PASS / 9 SKIP
- Migration 변경 없음
- React 빌드 및 스포일러 검사 성공
- 실행한 자동화 테스트 실패 0건

이번 테스트 범위에서는 기존 기능 회귀 오류와 검증 대상 콘텐츠 보안 오류가 발견되지 않았습니다.

실제 콘텐츠 승인 및 독립 프로세스 간 E2E는 후속 검증 대상으로 유지합니다.
