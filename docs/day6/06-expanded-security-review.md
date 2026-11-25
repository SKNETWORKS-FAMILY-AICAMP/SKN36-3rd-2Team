# Day 6 - Security Review

## 1. 보안 통제

| Control | Verification |
|---|---|
| Service Token | PASS |
| Forged Token Rejection | PASS |
| Session Ownership | PASS |
| Revision Validation | PASS |
| Unpublished Evidence Gate | PASS |
| E26 Section Gate | PASS |
| NPC Knowledge Gate | PASS |
| Duplicate Score Prevention | PASS |
| Story Event Gate | PASS |
| Chapter Bypass Prevention | PASS |
| Django Failure Handling | PASS |
| Neo4j Transaction Rollback | PASS |
| Read-only MCP Search | PASS |

## 2. 콘텐츠 보안

- E26은 A 구획만 공개한다.
- E26 B/C 및 E30은 차단한다.
- E07은 미공개 상태를 유지한다.
- 미승인 NPC 카드 77개는 공개하지 않는다.
- 승인되지 않은 확장 Graph 관계는 반환하지 않는다.
- 검색 결과는 서버 신뢰 원본과 대조한다.

## 3. 세션 및 상태 무결성

- 세션 소유권 확인
- 최신 Revision 확인
- 상태 변경 원자적 저장
- 중복 획득 및 중복 점수 방지
- 다른 세션의 증거 및 이벤트 접근 제한
- 읽기 전용 검색의 상태 변경 방지

## 4. 장애 대응

- Django 연결 오류 및 Timeout 처리
- 콘텐츠 검증 실패 시 Fail Closed
- 이전 MCP Context 거부
- 잘못된 토큰 요청 거부

## 5. 데이터 격리

- 임시 게임 SQLite 사용
- 기존 Django DB의 읽기 전용 복제
- 임시 Django 포트 8002/8003 사용
- Neo4j 전용 테스트 포트 7688 사용
- 테스트 종료 후 임시 환경 정리

## 6. 운영 전 보완

- 토큰 및 비밀 정보 외부 관리
- 내부 API의 네트워크 접근 제한
- 예상된 MCP 권한 거부 Traceback 정리
- HTTPS 및 배포 환경 보안 설정
- 콘텐츠 원본 및 Manifest 공급 절차
- 챕터 정책의 정식 승인 및 릴리스 바인딩
- NPC 생성 응답의 정보 유출 추가 평가

이번 검토는 구현된 통제 및 테스트 결과에 대한 검토이다.
전체 운영 보안 인증이나 침투 테스트를 의미하지 않는다.
