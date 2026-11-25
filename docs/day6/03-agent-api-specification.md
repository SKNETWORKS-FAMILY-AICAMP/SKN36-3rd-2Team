# Day 6 - Agent HTTP API Specification

> 관련 이슈: #157

## 1. 공통 경로

Base path:

`/api/games/{session_id}/agents`

모든 Agent API는 POST 방식이다.
인증된 세션 소유자만 호출할 수 있다.

## 2. Endpoint

| Method | Endpoint | Description |
|---|---|---|
| POST | /deduction | 증거 기반 추론 |
| POST | /hint | 조사 단계별 힌트 |
| POST | /assist | Deduction 및 Hint 협업 |

## 3. Request Schema

### Deduction

```json
{
  "message": "현재 확보한 증거를 분석해 주세요.",
  "expectedRevision": 3
}
```

### Hint

```json
{
  "level": 2,
  "expectedRevision": 3
}
```

### Assist

```json
{
  "message": "현재 확보한 증거의 연관성을 알려 주세요.",
  "level": 2,
  "expectedRevision": 3
}
```

## 4. Validation

| Field | Rule |
|---|---|
| message | 공백 제거 후 1~200자 |
| expectedRevision | 0 이상의 정수 |
| level | 1~3 정수 |
| Hint default level | 1 |
| Assist default level | 2 |
| Extra fields | 허용하지 않음 |

서버는 클라이언트가 보낸 증거 수집 상태를 신뢰하지 않는다.

## 5. Response Schema

### DeductionResponse

- agentType: string
- text: string
- sourceIds: array[string]
- status: string
- verdict: string
- contradiction: string
- revision: integer

### HintResponse

- agentType: string
- text: string
- sourceIds: array[string]
- level: integer
- status: string
- chapter: string
- collectedCount: integer
- suggestedCharacterId: string or null
- revision: integer

### AssistResponse

- deduction: DeductionResponse
- hint: HintResponse
- revision: integer

정상 응답에는 Cache-Control: no-store를 적용한다.

## 6. HTTP Error Contract

| Status | Description |
|---:|---|
| 200 | 정상 실행 |
| 403 | 허용되지 않은 Agent 접근 또는 증거 사용 |
| 404 | 세션 없음 또는 소유권 불일치 |
| 409 | Revision 충돌 또는 조사 단계 불일치 |
| 422 | 요청 데이터 검증 실패 |
| 502 | 잘못된 MCP Tool 결과 |
| 503 | 외부 서비스 또는 실행 리소스 오류 |
| 504 | Agent 또는 MCP 실행 Timeout |

Django 승인 API의 ReadTimeout은 현재 ContentServiceError를
거쳐 MCP 실행 오류로 변환되므로 503으로 응답한다.
Agent 자체 실행 Timeout의 504와 구분한다.

## 7. Security

- HMAC 기반 세션 소유권 확인
- 요청 Revision 검증
- 서버 GameState 기반 접근 제어
- 근거 ID 검증
- 결과 캐싱 방지
- 내부 URL, 토큰, Traceback 응답 노출 방지
- 읽기 전용 실행

## 8. Implementation

- backend/src/crimescene/api/agent_http.py
- backend/src/crimescene/api/app.py
- backend/tests/test_agent_http.py

신규 API 테스트: 60 PASS
실제 API 연동 테스트: Deduction, Hint, Assist 모두 PASS

FastAPI TestClient로 실제 Router를 검증했다.
별도 Uvicorn 서버를 통한 외부 HTTP 및 프론트엔드 연동은
후속 검증 대상이다.
