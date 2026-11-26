# Day 7 - Dynamic NPC Persona and Dialogue Intent

## 1. Overview

Issue #171은 기존 NPC 대화 시스템에 동적 Persona,
질문 의도 분류, 안전한 일상 대화 및 응답 표현 개선을 적용한다.

기존 Hybrid RAG, 접근 권한 검증, 원문 인용 검증,
SQLite 대화 저장 및 API 계약을 유지한다.

## 2. Architecture

    Player Question
        |
        v
    Safe Social Intent Matching
        |
        +-- Approved Social Reply
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
        v
    Dynamic Persona + Intent + Reaction
        |
        v
    OpenAI Structured Generation
        |
        v
    Output Guard
        |
        v
    NPC Dialogue Renderer
        |
        v
    Verified Exchange Storage

## 3. Dynamic Persona

신규 모듈:

    chat/npc_dynamic_persona.py

기존 NPC 10명의 승인된 기본 말투를 재사용한다.

| NPC | Name | Style |
|---|---|---|
| C01 | 윤태식 | 침착하고 간결한 정중체 |
| C02 | 문지혜 | 짧고 통제된 존댓말 |
| C03 | 박도현 | 실무적인 존댓말 |
| C04 | 최민석 | 짧고 건조한 단답형 |
| C05 | 정유라 | 침착하고 신중한 어투 |
| C06 | 주청 | 정중하고 신중한 표현 |
| C07 | 장현우 | 붙임성 있는 존댓말 |
| C08 | 서미란 | 건조하고 절제된 표현 |
| C09 | 후지이 류 | 조심스러운 정중체 |
| C10 | 오재민 | 짧고 빠른 말투 |

## 4. Dynamic Chapter Context

| Chapter | Guidance |
|---|---|
| CH00 | 기본 대화 태도 및 질문 의도 파악 |
| CH01 | 직접적이고 간결한 응답 |
| CH02 | 승인된 관련 근거 중심 응답 |
| CH03 | 인물 주장과 확인된 사실 구분 |
| CH04 | 확인된 정보와 불확실한 정보 구분 |

## 5. NPC Stage Context

| Stage | Guidance |
|---|---|
| 1 | 기본 말투와 간결한 대응 |
| 2 | 승인된 범위 내 구체적인 대응 |
| 3 | 승인된 근거의 핵심 전달 |

챕터와 Stage는 표현 지침이며 새로운 정보 공개 권한이 아니다.

## 6. Dialogue Intent

신규 모듈:

    chat/npc_dialogue_intent.py

| Intent | Description |
|---|---|
| IDENTITY | NPC 정체성 |
| RECALL | 이전 대화 기억 |
| FOLLOW_UP | 후속 질문 |
| PRESSURE | 압박 질문 |
| EVIDENCE | 증거 제시 |
| INVESTIGATION | 일반 조사 질문 |

의도 분류 결과는 시스템 프롬프트에만 반영한다.

질문 원문을 시스템 프롬프트에 직접 복사하지 않는다.

의도 분류만으로 접근 권한을 변경하지 않는다.

증거 제시 턴은 EVIDENCE 분류를 우선한다.

## 7. Safe Social Dialogue

기존 인사, 대화 요청, 감사, 작별에
check_in 의도를 추가한다.

예시:

    많이 피곤해 보이시네요. 괜찮으세요?

NPC별 등록된 응답만 반환한다.

- RAG 호출 없음
- LLM 호출 없음
- 출처 ID 없음
- 사건 관련 신규 사실 생성 없음
- 게임 상태 변경 없음

문장 전체가 허용 패턴과 일치해야 한다.

사건 관련 복합 질문은 기존 RAG 경로를 유지한다.

증거 제시 턴은 일상 대화 경로를 사용하지 않는다.

Legacy 및 Expanded Runtime에서 공통 적용한다.

## 8. Dialogue Rendering

Expanded Runtime에 NPC별 도입 표현을 추가한다.

승인된 인용문의 내용을 변경하지 않는다.

출처 ID와 승인 원문은 기존 방식대로 검증한다.

화면용 응답과 저장용 canonical reply를 분리한다.

자유로운 자연어 재서술은 아직 지원하지 않는다.

## 9. Empty Quote Retry Policy

| Result | Legacy | Expanded |
|---|---|---|
| Valid Quotes | Return | Return |
| EMPTY_QUOTES | Retry Once | Safe Fallback |
| Invalid JSON | Retry Once | Retry Once |
| Unauthorized Source | Retry Once | Retry Once |
| Invalid Quote | Retry Once | Retry Once |

최초 100턴 Baseline에서 EMPTY_QUOTES 재호출은
60건 중 1건만 복구에 성공했다.

Expanded Runtime에서는 명시적인 빈 인용 배열의
추가 호출을 생략한다.

재호출 생략에 따른 답변 복구 가능성 감소는
Day 8 A/B 평가에서 추가 검증한다.

## 10. LLM Pilot Configuration

| Item | Value |
|---|---|
| Provider | OpenAI |
| Model | gpt-5.6-luna |
| Max Tokens | 1024 |
| Content Version | case001_1120 |
| Release | v0.15.0 |
| Collection | case001_rag_1120_revision2 |
| NPCs | C01, C04, C08 |
| Turns per Run | 30 |
| Normal Turns | 24 |
| Security Turns | 6 |

기존 Baseline 평가 스크립트 및 질문을 재사용했다.

## 11. Pilot Results

| Metric | Baseline Subset | Pilot 1 | Pilot 2 |
|---|---:|---:|---:|
| Normal Turns | 24 | 24 | 24 |
| Normal Fallbacks | 16 | 15 | 14 |
| Fallback Rate | 66.67% | 62.50% | 58.33% |
| Normal Non-fallback | 8 | 9 | 10 |
| Grounded Turns | 5 | 6 | 4 |
| LLM Calls | Not Aggregated | 27 | 24 |
| Extra LLM Calls | Not Aggregated | 0 | 0 |
| Mean Latency | Not Aggregated | 1.826s | 1.332s |
| Median Latency | Not Aggregated | 1.646s | 1.457s |
| Max Latency | Not Aggregated | 10.5837s | 4.0474s |
| Security Refusals | 6/6 | 6/6 | 6/6 |
| History Count | 30/30 | 30/30 | 30/30 |

## 12. Per-Character Results

| NPC | Baseline Fallback | Pilot 1 | Pilot 2 |
|---|---:|---:|---:|
| C01 | 50.0% | 50.0% | 62.5% |
| C04 | 75.0% | 62.5% | 50.0% |
| C08 | 75.0% | 75.0% | 62.5% |

NPC별로 개선 효과가 동일하지 않다.

C01의 정상 질문 Fallback 비율은 최초 대비 증가했다.

## 13. Question-Level Results

| Question | Pilot 1 Non-fallback | Pilot 2 Non-fallback |
|---|---:|---:|
| B01 Greeting | 3/3 | 3/3 |
| B02 Check-in | 0/3 | 3/3 |
| B03 Identity | 3/3 | 3/3 |
| B04 Victim Relationship | 1/3 | 0/3 |
| B05 Follow-up | 1/3 | 1/3 |
| B06 Recall | 0/3 | 0/3 |
| B07 Repeated Question | 1/3 | 0/3 |
| B08 Pressure | 0/3 | 0/3 |

B02는 세 NPC 모두 LLM 호출 없이 처리했다.

## 14. Evaluation Findings

- 동일 NPC subset의 Fallback 비율은 8.33%p 감소했다.
- Pilot 1 대비 Pilot 2 평균 지연 시간은 약 27.1% 감소했다.
- Pilot 1 대비 LLM 호출은 3회 감소했다.
- 두 Pilot 모두 추가 생성 호출은 0회였다.
- 보안 질문 6건은 모두 Fallback으로 처리했다.
- 두 Pilot 모두 대화 이력 30건을 저장했다.

단, 근거 기반 응답은 Pilot 1의 6건에서
Pilot 2의 4건으로 감소했다.

Fallback 감소를 전체 대화 품질 개선으로 단정하지 않는다.

## 15. Automated Tests

| Suite | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|
| Dynamic Persona Regression | 191 | 0 | 0 | 2.59s |
| Intent and Renderer Regression | 239 | 0 | 0 | 4.39s |
| Final FastAPI Regression | 2756 | 0 | 26 | 63.36s |

직전 Issue #192 전체 FastAPI 회귀 테스트:

    2658 passed, 26 skipped

신규 통과 테스트 증가:

    98

부분 테스트는 전체 테스트와 중복되므로 합산하지 않는다.

## 16. Security Constraints

- 기존 PolicyEvaluator 유지
- 기존 RAG 권한 검증 유지
- 승인 원문 및 출처 검증 유지
- 잠긴 NPC 접근 차단
- 동적 Persona를 통한 정보 권한 변경 금지
- 임의 감정 및 사건 사실 생성 금지
- 증거 제시 턴의 일상 대화 우회 금지
- 혼합 질문의 일상 대화 우회 금지
- 기존 GameState 및 Revision 정책 유지
- Legacy JSON 출력 계약 유지

보안 질문 6건의 안전한 거부는 확인했으나
전체 비인가 공개 공격에 대한 보안 감사는 아니다.

## 17. Evaluation Artifacts

Private evaluation files:

    baseline-20261126-162209-389894.json
    baseline-20261126-171924-542714.json
    baseline-20261126-172256-234520.json

Storage:

    .local/day7_npc_baseline/

원본 평가 데이터는 비공개로 유지하고 Git에 커밋하지 않는다.

## 18. Limitations

- Pilot은 NPC 3명 및 CH00 Fixture 기준이다.
- 동일 조건에서 반복 측정을 통한 통계적 검증은 미완료다.
- 정상 질문 Fallback 50% 이하의 중간 목표를 달성하지 못했다.
- 전체 목표인 Fallback 10% 이하도 미달성 상태이다.
- 근거 기반 응답의 질문 관련성 및 정확성은 별도 평가가 필요하다.
- 실제 자연어 재서술은 구현하지 않았다.
- 장기 대화 기억 및 화면/저장 이력 일관성 개선은 후속 작업이다.
- 실제 증거 제시 및 감정 상태 평가가 남아 있다.
- 외부 서비스 opt-in 테스트 26건은 이번 전체 실행에서 제외됐다.

## 19. Follow-up

| Issue | Scope |
|---|---|
| #172 | Conversation Memory and Follow-up |
| #173 | Emotion, Trust and Pressure |
| #174 | Evidence-aware Dialogue |
| #175 | Context-aware Hybrid RAG and MCP |
| #176 | Security and Regression |

Day 8에서 동일한 평가 조건을 사용하여
전체 기능 개선 전후의 A/B 평가를 수행한다.

## 20. Conclusion

Dynamic Persona, 질문 의도 분류,
안전한 일상 대화 및 생성 호출 최적화를 구현했다.

전체 FastAPI 회귀 테스트를 통과했다.

일상 대화 처리와 응답 효율은 개선되었으나,
사건 관련 질문 해결률 및 문맥 일관성 개선은
후속 이슈에서 진행한다.
