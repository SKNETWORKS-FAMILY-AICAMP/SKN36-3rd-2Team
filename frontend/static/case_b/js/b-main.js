// =============================================================
// b-main.js — B 화면 시작 파일 (모든 파일 중 가장 마지막에 불러옵니다)
//   1) 게임 세션을 받고  2) 증거 목록을 받고  3) 화면을 그리고  4) 새 알림을 확인합니다.
//   버튼과 기능을 연결하는 곳도 여기입니다.
//
// ⚠ 세션 ID를 어디에 저장할지는 아직 확정되지 않았습니다(공유안 5번).
//   아래 저장 방식은 데모용 임시입니다. 계약이 정해지면 A의 store.js 방식으로 바꿉니다.
//   세션을 누가 만드는지(메인 화면 START)도 A와 정합니다.
// =============================================================
window.B = window.B || {};

(function () {
  var S = B.store, $ = B.$;
  var SESSION_KEY = B.config.STORAGE_PREFIX + 'sessionId';

  function bind(id, fn) { var el = $(id); if (el) el.onclick = fn; }

  function start() {
    B.ensureModal();
    bind('b-evidence-btn', B.evidence.open);
    bind('b-relations-btn', B.relations.open);
    bind('b-records-btn', B.records.open);
    bind('b-accuse-btn', B.accuse.open);

    // 화면 위쪽 챕터·증거 개수 표시
    S.on(function () {
      if ($('b-chapter')) $('b-chapter').textContent = S.game.chapter;
      if ($('b-evidence-count')) $('b-evidence-count').textContent = '· ' + S.evidence.length + '개';
    });

    var saved = null;
    try { saved = localStorage.getItem(SESSION_KEY); } catch (e) { /* 무시 */ }

    var getSession = (saved && !B.config.USE_MOCK)
      ? (S.game.sessionId = saved, B.api.getGame().catch(function () { return B.api.createGame(); }))
      : B.api.createGame();

    getSession.then(function (g) {
      // 프롤로그 상태면 조사 단계로 넘깁니다. A 오프닝과 붙인 뒤에는
      // A가 먼저 부르므로 여기서는 PROLOGUE가 아닐 때 그냥 지나갑니다.
      if (g.phase === 'PROLOGUE' && B.config.AUTO_PROLOGUE) {
        S.game.sessionId = g.sessionId;
        return B.api.completePrologue();
      }
      return g;
    }).then(function (g) {
      S.setGame(g);
      try { localStorage.setItem(SESSION_KEY, g.sessionId); } catch (e) { /* 무시 */ }
      return B.evidence.refresh();
    }).then(function () {
      B.interview.render();
      return B.events.check();
    }).catch(function (e) {
      B.toast(e.message);
      B.interview.render();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
