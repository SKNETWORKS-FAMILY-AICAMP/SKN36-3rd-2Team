# 마지막 기록: 졸업하지 못한 밤 (프론트엔드)

React + Vite + TypeScript. 백엔드 없이 mock 모드로 동작한다.

    npm install
    npm run dev        # 개발 서버 (http://localhost:5173)
    npm run build      # 배포 빌드(dist/)
    npm run preview    # 빌드 결과 미리보기

실제 백엔드 연결: `.env.example`을 `.env`로 복사해 `VITE_API_MODE=http`, `VITE_API_BASE_URL` 설정.

## 화면 경로 (HashRouter)
`/#/` 메인 · `/#/story` · `/#/chat/C01` · `/#/evidence` · `/#/relations` · `/#/notes` · `/#/accuse` · `/#/final`
mock 모드에서 `/#/chat?debug`, `/#/relations?debug`로 개발용 패널(전원 해금, 증거 획득, 초기화, 관계선 많이 보기)이 열린다.

## 이미지 교체
`public/assets/` 아래 파일명만 같게 덮어쓰면 코드 수정 없이 교체된다.
- `album/<ID>.webp` : 2016 앨범 타일 (V01, C01~C10, M01). 대화·관계도·지목 화면의 인물 사진도 현재는 이것을 쓴다
- `characters/<ID>_calm.webp` : 2026 인물 입상(대화 화면 왼쪽). 파일이 없으면 앨범 타일로 대체된다
- `group/group2016.webp` : 2016 단체사진 (메인 화면)
- `backgrounds/bg_poster.webp` : 학교 전경 사진 (현재 미사용, 스토리 첫 장면은 코드로 그린 SVG 장면)
- 스토리 장소 배경 4개는 `src/components/PlaceScene.tsx`의 코드 그림이다. 사진으로 바꾸려면 이 컴포넌트에서 해당 장소를 `<img>`로 교체한다

표시 이름·이미지 경로는 `src/data/characters.ts` 한 곳에서 관리한다.

## 개발·점검 도구 (11/8 추가)
- `npm run spoiler` : dist/src에 정답·관리자 문서 관련 문자열이 섞였는지 검사 (빌드 후 실행)
- `/chat?debug` 패널: 전원 해금 / 증거 획득 / **증거 10칸** / 초기화
- mock 지목 결과 강제: 콘솔에서 `localStorage.setItem('serin-mock-force', 'ESTIMATED' | 'NOT_ENOUGH_EVIDENCE' | 'GAME_OVER' | 'DEEP')` (지우면 기본 흐름)
- 백엔드와 미확정인 동작은 `src/config.ts` 의 값으로 바꾼다 (`ESTIMATED_ENDS_GAME`, `SHOW_COLLECTION_PERCENT`)
- 연결 방식 전환(빌드 없이): 주소 뒤에 `?api=mock` / `?api=http` / `?api=reset` (예: `http://localhost:4173/?api=mock#/`). mock일 때 화면 왼쪽 아래에 "시연용 데이터" 표시
- 대화 응답 대기 한도 기본 90초(`VITE_CHAT_TIMEOUT_MS`), 넘으면 "다시 시도" 안내. 자세한 시연 방법은 `발표-실행-안내.md`
- 17:15 검토 반영: 지목 결과 먼저 저장 후 상태 갱신, 새 세션 생성 시 노트·기록 초기화, 대화 로딩 표시, 지목 확정 모달에 증거 목록, 실패 후 선택 유지, 도입부 진행 저장, 새로 시작 확인 모달(자체 UI)
