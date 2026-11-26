# Day 7 - NPC Emotional State and Trust

## 1. Overview

Issue #173은 기존 NPC Conversation Memory를 활용하여
NPC별 신뢰도, 긴장도, 경계심 및 감정 상태를 계산한다.

감정 상태는 대화 표현에만 영향을 주며
게임 진행 상태와 정보 공개 권한을 변경하지 않는다.

## 2. Architecture

    Player Question
        |
        v
    NPC Session Validation
        |
        v
    Conversation History
        |
        v
    Deterministic Emotion Engine
        |
        +-- Trust
        +-- Stress
        +-- Guard
        |
        v
    NPC Mood Classification
        |
        +-- Emotion Prompt
        +-- Emotion Renderer
        |
        v
    Authorized Quote Validation
        |
        v
    Verified Display Persistence

기존 RAG 승인 및 출력 검증 경로를 유지한다.
Runtime에서 감정 지침은 승인된 응답 계획에만 적용한다.

## 3. Implementation Files

| File | Description |
|---|---|
| npc_emotional_state.py | 감정 상태 및 민감도 계산 |
| npc_chat_runtime.py | 감정 상태 계산과 Runtime 연결 |
| npc_natural_reply.py | 감정별 화면 응답 표현 |
| npc_history_display.py | 저장된 감정 표현 검증 |
| test_npc_emotional_state.py | 감정 및 격리 테스트 |
| test_npc_chat_runtime.py | Runtime 통합 테스트 |

## 4. Emotional State Model

NPCEmotionalState는 immutable dataclass로 구현한다.

| Attribute | Initial | Range |
|---|---:|---:|
| Trust | 50 | 0-100 |
| Stress | 20 | 0-100 |
| Guard | 20 | 0-100 |

모든 수치는 정수만 허용한다.
bool, float 및 범위를 벗어난 값은 거부한다.

## 5. NPC Sensitivity

| NPC | Pressure | Positive |
|---|---:|---:|
| C01 | 2 | 1 |
| C02 | 3 | 1 |
| C03 | 2 | 2 |
| C04 | 3 | 1 |
| C05 | 1 | 3 |
| C06 | 1 | 3 |
| C07 | 2 | 3 |
| C08 | 3 | 1 |
| C09 | 1 | 2 |
| C10 | 2 | 2 |

민감도는 초기 게임 밸런싱을 위한 설정값이다.

실제 인물의 심리, 범행 여부 또는
비공개 사건 설정을 나타내는 데이터가 아니다.

## 6. State Transition

Positive interaction:

    trust += 3 + positive_sensitivity
    stress -= 3
    guard -= 3

Pressure interaction:

    trust -= 4 + pressure_sensitivity
    stress += 10 + 4 * pressure_sensitivity
    guard += 18 + 4 * pressure_sensitivity

모든 수치는 0에서 100 사이로 제한한다.

동일한 일상 대화 유형은 계산 범위에서
한 번만 긍정적 상호작용으로 반영한다.

## 7. Mood Classification

다음 우선순위에 따라 상태를 결정한다.

| Priority | Mood | Condition |
|---:|---|---|
| 1 | TENSE | stress >= 70 |
| 2 | GUARDED | guard >= 45 |
| 3 | RELAXED | trust >= 75 and stress <= 25 |
| 4 | COOPERATIVE | trust >= 60 |
| 5 | NEUTRAL | Otherwise |

감정 상태는 사건의 진실 또는 범인의 유죄를 의미하지 않는다.

## 8. Conversation Window

- 최대 최근 8턴을 사용한다.
- 이전 대화 최대 7건과 현재 질문을 계산한다.
- 미래 revision 및 음수 revision을 제외한다.
- 유효하지 않은 과거 질문은 제외한다.
- Session ID와 NPC ID로 격리된 기존 이력을 사용한다.
- 과거 NPC 응답 원문과 출처를 감정 지침에 삽입하지 않는다.
- 현재 증거 제시 턴은 기존 전용 반응 경로를 유지한다.

감정 상태는 영구적으로 누적되는 수치가 아니다.
최근 대화 범위에서 결정론적으로 재계산한다.

## 9. Emotion Prompt

감정 상태에 따라 서버가 관리하는 표현 지침을 추가한다.

- 기본적인 대화 태도
- 협조적인 태도
- 차분하고 부담 없는 표현
- 신중하고 절제된 태도
- 짧고 통제된 표현

수치 자체는 프롬프트에 노출하지 않는다.

사용자의 임의 입력으로 감정 시스템 지침을
변경하거나 권한을 획득할 수 없다.

기존 승인 원문 및 JSON 출력 계약을 유지한다.

## 10. Emotion Renderer

NPC 10명에 대해 감정별 도입 표현을 제공한다.

- COOPERATIVE: 10 expressions
- RELAXED: 10 expressions
- GUARDED: 10 expressions
- TENSE: 10 expressions

총 40개의 서버 관리 표현을 추가한다.

NEUTRAL은 기존 표현을 재사용한다.

감정 표현은 검증된 인용문 앞에 적용하며
인용문의 내용이나 순서는 변경하지 않는다.

근거가 없는 경우 기존 Fallback을 유지한다.

현재 증거 제시 반응은 기존 전용 표현을 우선한다.

## 11. Display Persistence

Issue #172에서 구축한 display_text 저장 구조를 재사용한다.

기존 Canonical Text와 출처는 변경하지 않는다.

History Validator에 신규 감정 표현을 추가하여
SQLite 재접속 이후에도 저장된 말풍선을 복원한다.

기존 Neutral, Repeated, Evidence 표현도 계속 허용한다.

## 12. Database and API Compatibility

| Item | Change |
|---|---|
| SQLite Schema | None |
| GameState Schema | None |
| HTTP API Contract | None |
| RAG Access Policy | None |
| MCP Tool Contract | None |
| Additional LLM Calls | None |

Legacy Runtime에는 신규 감정 프롬프트를 적용하지 않는다.

## 13. Security Verification

- NPC별 감정 상태 격리
- 플레이어별 감정 상태 격리
- 잠긴 NPC 접근 거부
- 잘못된 NPC ID 거부
- 미래 revision 기록 제외
- 감정 수치 범위 검증
- 반복 일상 대화의 신뢰도 무제한 상승 제한
- Prompt Injection 원문 삽입 방지
- GameState 변경 방지
- 승인되지 않은 진술 생성 방지
- 다른 NPC의 도입 표현 적용 방지
- 변조된 Display Text 거부
- 기존 Fallback 유지
- Legacy Runtime 호환

감정 수치는 접근 권한 판정에 사용하지 않는다.

## 14. Actual OpenAI Pilot

| Item | Value |
|---|---|
| Provider | OpenAI |
| Model | gpt-5.6-luna |
| Max Tokens | 1024 |
| Runtime | case001_1120 |
| Release | v0.15.0 |
| RAG Collection | case001_rag_1120_revision2 |
| RAG Records | 138 |
| Graph Nodes | 42 |
| Graph Edges | 111 |
| Published Graph Edges | 0 |
| NPCs | C01, C04, C08 |
| Total Turns | 30 |
| Normal Turns | 24 |
| Security Turns | 6 |

## 15. Pilot Results

| Metric | Issue #172 | Issue #173 |
|---|---:|---:|
| Normal Turns | 24 | 24 |
| Normal Fallbacks | 11 | 12 |
| Fallback Rate | 45.83% | 50.00% |
| Non-fallback | 13 | 12 |
| Grounded Turns | 4 | 3 |
| LLM Calls | 21 | 21 |
| Extra LLM Calls | 0 | 0 |
| Mean Latency | 1.457s | 1.652s |
| Median Latency | 1.430s | 1.970s |
| Max Latency | 11.2142s | 6.7902s |
| Security Fallbacks | 6/6 | 6/6 |
| History Count | 30/30 | 30/30 |

Fallback 비율은 4.17 percentage points 증가했다.

평균 응답 시간은 약 13.4% 증가했으며,
최대 응답 시간은 약 39.4% 감소했다.

단일 Pilot 실행이므로 변경사항과 성능 변동 사이의
인과관계를 확정할 수 없다.

## 16. Question-level Results

| Question | Issue #172 | Issue #173 |
|---|---:|---:|
| B01 Greeting | 3/3 | 3/3 |
| B02 Check-in | 3/3 | 3/3 |
| B03 Identity | 3/3 | 3/3 |
| B04 Victim Relationship | 0/3 | 0/3 |
| B05 Follow-up | 0/3 | 0/3 |
| B06 Recall | 3/3 | 3/3 |
| B07 Repeated Question | 1/3 | 0/3 |
| B08 Pressure | 0/3 | 0/3 |

Non-fallback 기준이며 의미적 정답률이 아니다.

## 17. Per-NPC Results

| NPC | Normal Fallbacks | Grounded | LLM Calls | Mean Latency |
|---|---:|---:|---:|---:|
| C01 | 4/8 | 1 | 7 | 1.812s |
| C04 | 4/8 | 1 | 7 | 1.559s |
| C08 | 4/8 | 1 | 7 | 1.585s |

각 NPC의 대화 이력 10건이 모두 저장되었다.

## 18. Target Achievement

| Target | Expected | Actual | Status |
|---|---|---|---|
| Normal Fallback | <=35% | 50% | Not Met |
| B08 Pressure | 3/3 | 0/3 | Not Met |
| B06 Recall | 3/3 | 3/3 | Met |
| LLM Calls | <=21 | 21 | Met |
| Security Fallbacks | 6/6 | 6/6 | Met |
| History Count | 30/30 | 30/30 | Met |
| NPC Isolation | Pass | Pass | Met |
| Session Isolation | Pass | Pass | Met |
| SQLite Reopen | Pass | Pass | Met |

Seven of nine combined evaluation targets met.

## 19. Automated Tests

| Suite | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|
| Initial Emotion Regression | 306 | 0 | 0 | 7.64s |
| Runtime and Isolation | 174 | 0 | 0 | 14.75s |
| FastAPI Full Regression | 2942 | 0 | 26 | 185.32s |

직전 #172 전체 회귀 결과는 2841 passed였다.
이후 HTTP 테스트 4건을 추가하고 별도로 검증했다.

#172의 예상 최종 통과 건수 2845건을 기준으로
현재 전체 통과 건수는 97건 증가했다.

중복되는 부분 테스트는 합산하지 않는다.

## 20. Skipped Tests

| Category | Count |
|---|---:|
| External live service integration | 14 |
| Symbolic link unavailable | 1 |
| Private image opt-in integration | 2 |
| Neo4j integration | 6 |
| Ollama embedding integration | 3 |
| Total | 26 |

전체 회귀에서 제외된 외부 서비스 테스트는
Day 8 통합 검증에서 별도로 실행한다.

## 21. Evaluation Artifact

Private result:

    .local/day7_npc_baseline/
    baseline-20261126-180146-830922.json

실제 Pilot 원본은 Git에 커밋하지 않는다.

## 22. Limitations

- 감정 상태는 최근 8턴 기반으로 재계산한다.
- 오래된 대화의 영향은 계산 범위에서 제외될 수 있다.
- 과거 증거 제시 여부는 이력에 별도로 저장되지 않는다.
- 감정 민감도는 초기 게임 밸런싱 설정이다.
- 실제 감정 표현의 자연스러움은 추가 평가가 필요하다.
- Pilot은 NPC 3명과 CH00 Fixture 기준이다.
- 연속 추궁 및 긴장 완화 시나리오가 충분하지 않다.
- 근거 부족 Fallback은 감정 상태로 우회하지 않는다.
- Fallback 감소 및 압박 질문 목표는 달성하지 못했다.
- 감정 Prompt가 성능 변동의 원인인지는 확정하지 못했다.
- 공개 Graph Edge가 없는 상태에서 평가했다.
- 전체 외부 서비스 E2E 테스트는 남아 있다.

## 23. Follow-up

| Issue | Scope |
|---|---|
| #174 | Evidence-aware NPC Dialogue |
| #175 | Context-aware Hybrid RAG and MCP |
| #176 | Security and Integration Regression |

#175에서는 검색 후보 관련성, RRF Fusion,
권한 필터링 전후 후보 수, 빈 quotes 반환 원인,
반복 진술 차단 및 Graph 검색 기여도를 분석한다.

Day 8에서는 동일 설정의 반복 A/B 평가와
연속 추궁 및 긴장 완화 시나리오를 검증한다.

## 24. Conclusion

기존 Conversation Memory를 활용하여
NPC별 결정론적 감정 상태를 구현했다.

감정 상태에 따른 Prompt 및 화면 표현을 추가하고
기존 접근 권한과 출력 검증 정책을 유지했다.

FastAPI 전체 회귀 테스트 2942건을 통과했다.

실제 Pilot의 검색 관련 지표는 개선되지 않았으므로
후속 Hybrid RAG 개선 과제로 분리한다.
