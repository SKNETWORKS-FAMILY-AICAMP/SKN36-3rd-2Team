# Day 7 - NPC Conversation Memory

## 1. Overview

Issue #172는 NPC별 대화 기억, 후속 질문 문맥 연결,
반복 진술 일관성 및 화면 응답 영구 저장을 구현한다.

기존 SQLite 대화 저장소와 Hybrid RAG를 재사용하며,
별도의 Memory DB나 외부 Memory 프레임워크를 추가하지 않는다.

## 2. Architecture

    Player Question
        |
        v
    Session and NPC Validation
        |
        v
    Conversation Intent
        |
        +-- Recall
        |      |
        |      v
        |   Safe Memory Response
        |
        +-- Investigation / Follow-up
               |
               v
            Memory Search Context
               |
               v
            Hybrid RAG
               |
               v
            PolicyEvaluator
               |
               v
            Authorized Context
               |
               +-- Revalidated Repeat
               |
               +-- LLM Generation
               |
               v
            Output Guard
               |
               v
            NPC Display Renderer
               |
               v
    Atomic Exchange Persistence

## 3. Conversation Memory Builder

New module:

    chat/npc_conversation_memory.py

| Configuration | Value |
|---|---|
| Storage | Existing SQLite |
| Isolation | Session ID + NPC ID |
| Context Window | Latest 4 exchanges |
| Anchor Question Limit | 200 characters |
| Search Context Limit | 400 characters |
| Historical NPC Claims | Not used as search input |
| Additional LLM Calls | None |

과거 플레이어 질문은 신뢰할 수 없는 검색 입력으로 취급한다.

검색 문맥을 확장하더라도 기존 접근 권한 검증과
승인된 원문 검증을 변경하지 않는다.

## 4. Follow-up Retrieval

후속 질문으로 분류된 경우 최근 대화에서
구체적인 이전 질문을 찾아 검색 입력에 결합한다.

현재 질문은 LLM 입력에서 그대로 유지한다.

다음 상황에서는 문맥 확장을 제한한다.

- 미래 revision 기록
- 길이 제한 초과
- 일상 대화에 의한 문맥 단절
- Recall 또는 Pressure 질문
- 증거 제시 턴
- 유효하지 않은 이전 질문

## 5. Revalidated Repeat

동일 질문의 기존 답변이 현재 승인 원문 및
출처와 일치하는 경우 검증된 인용문을 재사용한다.

- 최근 4턴 범위
- 동일 질문만 허용
- 기존 출처 및 원문 재검증
- 기존 Output Guard 재사용
- 최신 동일 질문이 Fallback이면 이전 진술 복원 금지
- 증거 제시 턴의 재사용 금지

실제 Pilot에서는 반복 진술의 LLM 호출 생략 사례가
관측되지 않았다. 재사용 기능은 자동화 테스트로 검증했다.

## 6. Safe Memory Recall

New module:

    chat/npc_memory_recall.py

NPC 10명에 대한 안전한 회상 응답을 제공한다.

예시:

    Player:
    제가 아까 어떤 질문을 했는지 기억하세요?

    NPC:
    네. 직전 답변을 더 설명해 달라고 하셨습니다.

회상 응답은 서버가 관리하는 문장으로 구성한다.

- RAG 호출 없음
- LLM 호출 없음
- 출처 ID 없음
- 과거 질문 원문 복창 금지
- 과거 NPC 비공개 진술 재사용 금지
- 미래 revision 사용 금지
- 다른 NPC 또는 세션의 기록 사용 금지

자유로운 장기 기억이 아닌 직전 질문의 유형별 회상이다.

분류할 수 없는 질문은 안전한 재질문으로 처리한다.

## 7. Recall Persistence

일반 세션 저장소와 HTTP 원자적 저장소에서
실제 직전 질문을 기준으로 회상 응답을 재검증한다.

SQLite 원자적 저장에서는 BEGIN IMMEDIATE
트랜잭션 내부에서 이전 질문을 다시 조회한다.

검증 실패 시 GameState와 대화 기록을 저장하지 않는다.

기존 revision 증가 및 경쟁 요청 차단 정책을 유지한다.

## 8. Display Text Persistence

NPCExchange에 선택적 display_text 필드를 추가한다.

SQLite npc_exchanges 테이블에 nullable TEXT 컬럼을
추가하여 화면용 응답과 검증용 응답을 분리한다.

| Field | Purpose |
|---|---|
| user_message | Player question |
| npc_message | Canonical verified response |
| source_ids_json | Verified source IDs |
| state_revision | Exchange revision |
| display_text | Original rendered NPC response |

Canonical Text는 기존 Memory 검증에 사용한다.

Display Text는 실제 화면 응답 복원에 사용한다.

Expanded Runtime의 근거 기반 응답에 적용하며
Legacy Runtime의 기존 동작을 유지한다.

## 9. SQLite Compatibility Migration

기존 npc_exchanges 컬럼을 확인한 후
display_text 컬럼이 없는 경우에만 추가한다.

    ALTER TABLE npc_exchanges
    ADD COLUMN display_text TEXT;

- 기존 데이터 삭제 없음
- 기존 테이블 재생성 없음
- 반복 초기화 지원
- 기존 대화는 NULL 유지
- 신규 대화는 검증된 화면 응답 저장

기존 대화의 최초 말풍선 표현은 저장되지 않았으므로
완전한 복원이 불가능하다.

운영 DB 적용 전 백업을 권장한다.

## 10. Display Security

저장할 화면 응답은 다음 조건을 만족해야 한다.

- Canonical Text의 검증된 인용 내용 유지
- 인용문 순서 유지
- 해당 NPC의 서버 등록 표현만 사용
- 임의의 문장 추가 금지
- 내부 출처 메타데이터 노출 금지

변조된 화면 응답은 저장 단계에서 거부하거나
이력 조회 단계에서 안전한 Fallback으로 처리한다.

Display 검증은 저장된 Canonical Text와의 일치 검증이다.
이력 조회 시 전체 RAG 접근 권한을 다시 평가하는
기능까지 추가한 것은 아니다.

## 11. HTTP Compatibility

Existing endpoint:

    GET /api/games/{session_id}/chats/{character_id}

기존 ChatHistoryResponse 계약을 유지한다.

- sessionId
- characterId
- messages[].userMessage
- messages[].displayText

기존 세션 소유권 검증과 NPC 해금 검증을 유지한다.

이력 조회에 따른 GameState revision 변경은 없다.

## 12. Pilot Configuration

| Item | Value |
|---|---|
| Provider | OpenAI |
| Model | gpt-5.6-luna |
| Max Tokens | 1024 |
| Runtime | case001_1120 |
| Release | v0.15.0 |
| RAG Collection | case001_rag_1120_revision2 |
| NPCs | C01, C04, C08 |
| Total Turns | 30 |
| Normal Turns | 24 |
| Security Turns | 6 |

동일 NPC 및 기존 평가 질문을 사용했다.

## 13. Pilot Results

| Metric | Issue #171 | Issue #172 |
|---|---:|---:|
| Normal Turns | 24 | 24 |
| Normal Fallbacks | 14 | 11 |
| Fallback Rate | 58.33% | 45.83% |
| Non-fallback | 10 | 13 |
| Grounded Turns | 4 | 4 |
| Safe Non-grounded Turns | 6 | 9 |
| LLM Calls | 24 | 21 |
| Extra LLM Calls | 0 | 0 |
| Mean Latency | 1.332s | 1.457s |
| Median Latency | 1.457s | 1.430s |
| Max Latency | 4.0474s | 11.2142s |
| Security Refusals | 6/6 | 6/6 |
| History Count | 30/30 | 30/30 |

## 14. Question-level Results

| Question | Issue #171 | Issue #172 |
|---|---:|---:|
| B01 Greeting | 3/3 | 3/3 |
| B02 Check-in | 3/3 | 3/3 |
| B03 Identity | 3/3 | 3/3 |
| B04 Victim Relationship | 0/3 | 0/3 |
| B05 Follow-up | 1/3 | 0/3 |
| B06 Recall | 0/3 | 3/3 |
| B07 Repeated Question | 0/3 | 1/3 |
| B08 Pressure | 0/3 | 0/3 |

Non-fallback 기준이며 의미적 정답률과 동일하지 않다.

## 15. Per-NPC Results

| NPC | Issue #171 Fallback | Issue #172 Fallback |
|---|---:|---:|
| C01 | 5/8 | 3/8 |
| C04 | 4/8 | 4/8 |
| C08 | 5/8 | 4/8 |

## 16. Evaluation Findings

- 정상 질문 Fallback 3건 감소
- Fallback 비율 12.50 percentage points 감소
- LLM 호출 3회 감소
- Recall 질문 3/3 Non-fallback
- Recall LLM 호출 0회
- 추가 생성 호출 0회
- 보안 질문 6/6 안전한 거부
- 대화 이력 30/30 저장

근거 기반 응답은 4건으로 유지되었다.

후속 질문은 개선되지 않았으며
반복 질문 성공 1건도 LLM을 호출했다.

평균 응답 시간은 약 9.4% 증가했다.

C01의 최초 근거 기반 질문은 11.2142초가 소요되었다.
외부 서비스 초기화 또는 검색 지연 가능성이 있으나
상세 프로파일링 이전에는 원인을 확정할 수 없다.

## 17. Target Achievement

| Target | Expected | Actual | Status |
|---|---:|---:|---|
| Follow-up | 3/3 | 0/3 | Not Met |
| Recall | 3/3 | 3/3 | Met |
| Repeated Question | 3/3 | 1/3 | Not Met |
| Fallback Rate | <=40% | 45.83% | Not Met |
| Recall LLM Calls | 0 | 0 | Met |
| Total LLM Calls | <=21 | 21 | Met |
| Mean Latency | <=1.2s | 1.457s | Not Met |
| Security Refusals | 6/6 | 6/6 | Met |
| History Count | 30/30 | 30/30 | Met |

Five of nine pilot targets met.

## 18. Automated Tests

| Suite | Passed | Failed | Duration |
|---|---:|---:|---:|
| Initial Memory Regression | 200 | 0 | 4.21s |
| Recall Integration | 94 | 0 | 1.90s |
| Atomic Recall Regression | 101 | 0 | 2.30s |
| Display Persistence Regression | 198 | 0 | 4.60s |
| FastAPI Full Regression | 2841 | 0 | 72.70s |
| Final HTTP History Regression | 120 | 0 | 3.78s |

Full regression skipped: 26.

직전 Issue #171 전체 회귀 테스트는 2756 passed였다.

전체 회귀 실행 이후 HTTP 이력 테스트 4건을 추가했다.

해당 4건은 최종 HTTP 회귀 테스트에서 통과했다.

Expected final full count: 2845 passed.

최종 예상 건수는 전체 재실행 결과가 아니다.
중복되는 부분 테스트의 통과 건수는 합산하지 않는다.

## 19. Security Verification

- NPC별 기억 격리
- 플레이어 세션별 기억 격리
- 미래 revision 거부
- 오래된 revision 커밋 거부
- 조작된 회상 응답 거부
- SQLite 원자적 저장 및 롤백 유지
- 증거 제시 턴의 Memory 우회 방지
- 승인되지 않은 이전 인용문 재사용 금지
- 변조된 Display Text 거부
- SQLite 재접속 후 대화 복원
- 기존 SQLite 데이터 마이그레이션 검증
- 다른 플레이어 HTTP 이력 접근 차단
- 내부 출처 메타데이터 비노출

## 20. Evaluation Artifacts

Private pilot result:

    .local/day7_npc_baseline/
    baseline-20261126-174726-242996.json

실제 평가 원본은 Git에 커밋하지 않는다.

## 21. Limitations

- Pilot은 NPC 3명과 CH00 Fixture 기준이다.
- 후속 질문과 반복 질문의 실제 성공률은 추가 개선이 필요하다.
- Fallback 40% 이하의 중간 목표는 달성하지 못했다.
- 전체 대화의 의미적 정확성은 별도 평가가 필요하다.
- Recall은 자유로운 장기 기억이 아니다.
- 과거 대화의 최초 화면 응답은 완전히 복원할 수 없다.
- HTTP History 테스트는 저장된 Fixture 기반이다.
- 실제 OpenAI HTTP 생성부터 이력 복원까지의 E2E 검증은 남아 있다.
- 이력 조회 시 현재 접근 권한 재평가는 별도 보안 검토가 필요하다.
- 외부 서비스 opt-in 테스트는 이번 전체 회귀에서 제외됐다.

## 22. Follow-up

| Issue | Scope |
|---|---|
| #173 | NPC Emotional State and Trust |
| #174 | Evidence-aware Dialogue |
| #175 | Context-aware Hybrid RAG and MCP |
| #176 | Security and E2E Regression |

Day 8에서 반복 A/B 평가 및 Cold/Warm 요청의
검색 및 생성 지연 시간을 분리하여 측정한다.

## 23. Conclusion

NPC별 대화 기억, 안전한 질문 회상,
후속 질문 검색 문맥 확장 및 반복 진술 재사용을 구현했다.

Canonical Text를 유지하면서 화면용 응답을 영구 저장한다.

기존 데이터 호환성과 원자적 저장 정책을 유지했으며
전체 회귀 및 추가 HTTP 이력 테스트를 통과했다.

사건 관련 답변의 검색 품질은 후속 이슈에서 개선한다.
