// =============================================================
// b-events.js — 새 수사 알림 (할 일 11)
//   GET  /story-events/pending  → 아직 확인 안 한 알림 목록
//   POST /story-events/{key}/ack → "확인" 누르면 서버에 알림
//   같은 알림을 두 번 띄우지 않도록 본 알림 번호를 브라우저에도 기록합니다.
// =============================================================
window.B = window.B || {};

B.events = (function () {
  var S = B.store, esc = B.esc, $ = B.$;
  var busy = false;

  function check() {
    if (busy) return Promise.resolve();
    busy = true;
    return B.api.pendingEvents().then(function (items) {
      var seen = S.load('seenEvents', []);
      var fresh = items.filter(function (ev) { return seen.indexOf(ev.eventKey) < 0; });
      // 이미 본 알림인데 서버에 확인이 안 간 경우(새로고침 등)는 조용히 확인만 보냅니다.
      items.filter(function (ev) { return seen.indexOf(ev.eventKey) >= 0; })
        .forEach(function (ev) { B.api.ackEvent(ev.eventKey).catch(function () {}); });
      return showInOrder(fresh);
    }).catch(function (e) {
      B.toast('알림을 불러오지 못했습니다: ' + e.message);
    }).then(function () { busy = false; });
  }

  // 알림을 하나씩 차례로 보여 줍니다.
  function showInOrder(list) {
    return list.reduce(function (chain, ev) {
      return chain.then(function () { return showOne(ev); });
    }, Promise.resolve());
  }

  function showOne(ev) {
    return new Promise(function (done) {
      B.openModal(ev.title || '새로운 수사 알림',
        '<p class="b-event-text">' + esc(ev.text || '') + '</p>' +
        '<button type="button" id="b-event-ok" class="b-primary">확인</button>', true);
      $('b-event-ok').onclick = function () {
        $('b-event-ok').disabled = true;
        B.api.ackEvent(ev.eventKey).then(function () {
          var seen = S.load('seenEvents', []);
          if (seen.indexOf(ev.eventKey) < 0) { seen.push(ev.eventKey); S.save('seenEvents', seen); }
          B.closeModal();
          done();
        }).catch(function () {
          $('b-event-ok').disabled = false;
          B.toast('확인 처리에 실패했습니다. 다시 눌러 주세요.');
        });
      };
    });
  }

  return { check: check };
})();
