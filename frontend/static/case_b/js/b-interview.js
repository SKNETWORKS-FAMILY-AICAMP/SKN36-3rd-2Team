// =============================================================
// b-interview.js — 면담실 (할 일 1·2·3·6)
//   1. 면담실 화면: 인물 초상 + 대화창 + 질문 입력
//   2. 대화 기록 표시: 이전 대화 불러오기, 최신 대사 강조
//   3. 진술 저장: 인물 대사 옆 "진술 저장" → 브라우저에 저장
//   6. 증거 1개 제시: 증거함에서 고른 증거가 입력창 위에 표시, 취소 가능
//
// 페이지에 필요한 자리:
//   <div id="b-people"></div>      왼쪽 면담 대상 목록
//   <div id="b-interview"></div>   가운데 면담실
// =============================================================
window.B = window.B || {};

B.interview = (function () {
  var S = B.store, esc = B.esc, $ = B.$;
  var sending = false;

  // ---- 왼쪽: 면담 대상 목록 (서버가 공개한 인물만) ----
  function renderPeople() {
    var box = $('b-people');
    if (!box) return;
    var ids = S.game.characters;
    box.innerHTML = '<h3>면담 대상</h3>' + (ids.length ? ids.map(function (id) {
      var p = B.roster[id] || { name: id, role: '' };
      return '<button type="button" class="b-person ' + (S.who === id ? 'active' : '') + '" data-b-who="' + esc(id) + '">' +
        esc(p.name) + '<small>' + esc(p.role) + '</small></button>';
    }).join('') : '<p class="b-muted">공개된 인물이 없습니다.</p>');
  }

  // ---- 가운데: 면담실 ----
  function renderRoom() {
    var box = $('b-interview');
    if (!box) return;
    if (!S.who) {
      box.innerHTML = '<div class="b-room-empty">왼쪽에서 면담할 인물을 선택하세요.</div>';
      return;
    }
    var p = B.roster[S.who] || { name: S.who };
    var log = S.logs[S.who] || [];
    var lastNpc = -1;
    log.forEach(function (m, i) { if (m.npc) lastNpc = i; });
    var sel = S.evidence.filter(function (e) { return e.id === S.selectedEvidence; })[0];

    box.innerHTML =
      '<div class="b-talk">' +
      '  <div class="b-portrait"><img src="' + esc(B.personImage(S.who)) + '" alt="' + esc(p.name) + '" ' +
      '       onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'b-muted\',textContent:\'인물 이미지 없음\'}))"></div>' +
      '  <div class="b-chat">' +
      '    <div class="b-titlebar"><b>' + esc(p.name) + '</b>' +
      '      <button type="button" id="b-latest">최신 대사</button></div>' +
      '    <div class="b-log" id="b-log">' +
      (log.length ? log.map(function (m, i) {
        return '<div class="b-msg ' + (m.npc ? 'npc' : 'me') + (i === lastNpc ? ' latest' : '') + '">' +
          '<b>' + esc(m.from) + '</b><p>' + esc(m.text) + '</p>' +
          (m.npc ? '<button type="button" class="b-pin" data-b-pin="' + i + '">진술 저장</button>' : '') +
          '</div>';
      }).join('') : '<p class="b-muted">질문을 입력하세요.</p>') +
      '    </div>' +
      '    <div class="b-chip-row">' +
      (sel ? '<span class="b-chip">제시할 증거: ' + esc(sel.title) +
        ' <button type="button" id="b-chip-cancel" aria-label="증거 선택 취소">✕</button></span>'
        : '<span class="b-muted">증거함에서 "한 개 제시"를 누르면 여기에 표시됩니다.</span>') +
      '    </div>' +
      '    <form id="b-chat-form" class="b-form">' +
      '      <input id="b-question" maxlength="' + B.config.QUESTION_MAX + '" autocomplete="off" ' +
      '        placeholder="' + (sel ? '증거와 함께 할 말을 적거나 비워 두세요' : '질문을 입력하세요') + '">' +
      '      <button type="submit" id="b-send"' + (sending ? ' disabled' : '') + '>' + (sending ? '답변 대기…' : '전송') + '</button>' +
      '    </form>' +
      '  </div>' +
      '</div>';

    $('b-latest').onclick = scrollToEnd;
    $('b-chat-form').onsubmit = send;
    if ($('b-chip-cancel')) $('b-chip-cancel').onclick = function () { S.selectedEvidence = null; render(); };
    scrollToEnd();
  }

  function scrollToEnd() {
    var log = $('b-log');
    if (log) log.scrollTop = log.scrollHeight;
  }

  function render() { renderPeople(); renderRoom(); }

  // ---- 인물 선택: 서버에 알리고, 이전 대화를 불러옵니다 ----
  function selectPerson(id) {
    if (S.game.characters.indexOf(id) < 0) return;      // 공개되지 않은 인물은 무시
    if (S.who !== id) S.selectedEvidence = null;        // 상대가 바뀌면 고른 증거를 비움
    S.who = id;
    render();
    B.api.select(id).then(function (g) {
      S.setGame(g);
      return B.api.chatHistory(id);
    }).then(function (messages) {
      var name = B.personName(id), list = [];
      messages.forEach(function (m) {
        list.push({ from: '수사관', text: m.userMessage, npc: false });
        list.push({ from: name, text: m.displayText, npc: true });
      });
      S.logs[id] = list;
      render();
    }).catch(function (e) { B.toast(e.message); });
  }

  // ---- 전송: 질문(+증거 1개) ----
  function send(e) {
    e.preventDefault();
    if (sending || !S.who) return;
    var text = $('b-question').value.trim();
    var ev = S.selectedEvidence;
    if (!text && !ev) return;
    var question = text || B.config.PRESENT_DEFAULT_QUESTION;
    var id = S.who;

    (S.logs[id] = S.logs[id] || []).push({
      from: '수사관', text: ev ? '[증거 제시: ' + titleOf(ev) + '] ' + question : question, npc: false
    });
    sending = true;
    render();

    B.api.chat(question, ev).then(function (r) {
      S.logs[id].push({ from: B.personName(id), text: r.reply || '', npc: true });
      if (ev) {
        var presented = S.load('presented', {});
        (presented[id] = presented[id] || []).push(ev);
        S.save('presented', presented);
      }
      S.selectedEvidence = null;
      sending = false;
      S.setGame(r.game);
      if (B.evidence) B.evidence.refresh();              // 새 증거가 생겼을 수 있음
      if (B.consent) B.consent.check(r.raw);            // E30 동의 신호 확인
      if (B.events) B.events.check();                   // 새 수사 알림 확인
      render();
    }).catch(function (err) {
      S.logs[id].pop();                                 // 실패한 질문은 기록에서 뺌
      sending = false;
      render();
      $('b-question').value = text;
      B.toast(err.message);
    });
  }

  function titleOf(id) {
    var e = S.evidence.filter(function (x) { return x.id === id; })[0];
    return e ? e.title : id;
  }

  // ---- 진술 저장 ----
  function pin(index) {
    var m = (S.logs[S.who] || [])[index];
    if (!m) return;
    var pins = S.load('pins', []);
    var dup = pins.some(function (p) { return p.who === S.who && p.text === m.text; });
    if (!dup) {
      pins.push({ who: S.who, from: m.from, text: m.text, savedAt: new Date().toISOString() });
      S.save('pins', pins);
    }
    B.toast(dup ? '이미 저장한 진술입니다' : '진술을 저장했습니다');
  }

  // ---- 증거함에서 "한 개 제시"를 눌렀을 때 ----
  function choose(evidenceId) {
    if (!S.who) { B.toast('먼저 면담할 인물을 선택하세요'); return false; }
    S.selectedEvidence = evidenceId;
    render();
    var q = $('b-question'); if (q) q.focus();
    return true;
  }

  // 버튼 클릭을 한곳에서 받습니다.
  document.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.bWho) selectPerson(b.dataset.bWho);
    if (b.dataset.bPin !== undefined) pin(+b.dataset.bPin);
  });

  S.on(renderPeople);

  return { render: render, selectPerson: selectPerson, choose: choose };
})();
