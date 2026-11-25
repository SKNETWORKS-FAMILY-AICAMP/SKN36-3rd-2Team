# B 화면 (면담·증거·관계도·수사 기록·최종 추리·엔딩)

## 바로 확인
`static/case_b/dev/demo.html`을 더블클릭 → 서버 없이 모의 응답으로 B 화면 전체를 눌러 볼 수 있습니다.
인물 초상은 기존 `frontend/public/assets/characters/`를 그대로 씁니다.

## 파일
| 파일 | 할 일 |
|---|---|
| js/b-config.js | 설정(모의/실제, 이미지 경로, 타임라인 끔) |
| js/b-roster.js | 인물 공개 정보 |
| js/b-ui.js | 모달·알림·글자 안전 처리 |
| js/b-store.js | B 상태(A의 common/store.js가 나오면 연결) |
| js/b-api.js | B가 부르는 서버 경로(요청은 common/api.js) |
| js/b-interview.js | 면담실·대화 기록·진술 저장·증거 1개 제시 |
| js/b-evidence.js | 증거함·상세·나란히 보기 |
| js/b-relations.js | 인물관계도 |
| js/b-records.js | 수사 기록(대화·진술·노트) |
| js/b-accuse.js | 최종 추리(1명) |
| js/b-ending.js | 엔딩 |
| js/b-events.js | 새 수사 알림·확인 |
| js/b-consent.js | E30 동의 모달 |
| js/b-main.js | 시작 |
| dev/b-mock.js, dev/demo.html | 개발용 — 배포 템플릿에 넣지 않음 |

## 서버 경로 (모두 `/api/games/{세션ID}` 뒤, dev 기준 확인)
인물 선택 `POST /characters/{id}/select` · 대화 `POST /chat {question, presentedEvidenceId}` · 이전 대화 `GET /chats/{id}` ·
증거 `GET /evidence`, `/evidence/{id}`, `/evidence/{id}/photo` · 관계도 `GET /relationships` ·
알림 `GET /story-events/pending`, `POST /story-events/{key}/ack` · 추리 `POST /accusations {suspectId, expectedRevision}` · 엔딩 `GET /ending`

## 주의
- 세션 ID 저장 위치는 미확정입니다. `b-main.js`는 데모용 임시 방식입니다.
- 서버는 제시 증거를 `E01~E10`만 받습니다(E11~E30은 백엔드 확인 필요).
- E30 동의 신호·API는 아직 없습니다(`b-config.js`의 `CONSENT_FLAG`).
- 점수·정답·해금 규칙은 코드에 넣지 않습니다. 증거 사진은 서버 주소로만 불러옵니다.
