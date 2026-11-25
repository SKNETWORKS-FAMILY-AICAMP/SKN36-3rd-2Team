// =============================================================
// b-ending.js — 엔딩 화면 (할 일 10)
//   GET /ending 의 title·message를 그대로 보여 줍니다.
//   엔딩 문장은 서버가 보냅니다. 프론트에 엔딩 문장을 적어 두지 않습니다.
//   (기존 React endingScenes.ts의 FULL·DEEP 문구는 옛 버전이라 쓰지 않습니다.)
// =============================================================
window.B = window.B || {};

B.ending = (function () {
  var esc = B.esc, $ = B.$;

  // 엔딩 종류별 도장 글자(판정 이름만 표시)
  var STAMP = {
    FULL: '사건 해결', DEEP: '사건 해결', ESTIMATED: '추정 성립',
    UNSOLVED: '수사 실패', NO_EVIDENCE: '수사 중단'
  };

  function show() {
    B.api.ending().then(draw).catch(function (e) { B.toast(e.message); });
  }

  function draw(r) {
    var old = $('b-ending'); if (old) old.remove();
    var el = document.createElement('section');
    el.id = 'b-ending';
    el.className = 'b-ending';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    var t = r.truth;
    el.innerHTML =
      '<div class="b-ending-card">' +
      '  <div class="b-stamp ' + (r.outcome === 'FULL' || r.outcome === 'DEEP' ? 'ok' : '') + '">' + esc(STAMP[r.outcome] || r.outcome || '') + '</div>' +
      '  <h2>' + esc(r.title || '') + '</h2>' +
      '  <p class="b-ending-msg">' + esc(r.message || '') + '</p>' +
      // 사건 정리는 서버가 보냈을 때만 보여 줍니다(게임이 끝난 뒤에만 옴).
      (t ? '<details class="b-truth"><summary>사건 정리</summary>' +
        '<p><b>범인</b> ' + esc(B.personName(t.perpetratorId)) + '</p>' +
        '<p><b>동기</b> ' + esc(t.motive) + '</p>' +
        '<p><b>사망 원인</b> ' + esc(t.causeOfDeath) + '</p>' +
        '<p><b>수법</b> ' + esc(t.crimeMethod) + '</p></details>' : '') +
      '  <div class="b-tile-actions"><button type="button" id="b-ending-close">닫기</button>' +
      '  <button type="button" id="b-ending-home" class="b-primary">처음으로</button></div>' +
      '</div>';
    document.body.appendChild(el);
    $('b-ending-close').onclick = function () { el.remove(); };
    // "처음으로"가 어느 주소로 갈지는 A(메인 화면 담당)와 정합니다.
    $('b-ending-home').onclick = function () { location.href = B.config.HOME_URL || './'; };
  }

  return { show: show };
})();
