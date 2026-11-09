// 백엔드와 아직 확정되지 않은 동작을 한곳에서 바꿀 수 있게 모아 둔 설정.
// 협의 결과에 따라 값만 바꾸면 된다. (docs: 백엔드-협의-정리.md)

/** #4 ESTIMATED 판정이 나오면 게임을 끝내고 최종 화면으로 보낸다. false면 계속 진행(서버가 gameOver 로 알려줄 때만 종료). */
export const ESTIMATED_ENDS_GAME = true

/** #5 수집 정도를 %로 보여준다. false면 확보 개수만 보여준다. 서버가 total 을 0 이하로 주면 자동으로 개수만 보여준다. */
export const SHOW_COLLECTION_PERCENT = true
