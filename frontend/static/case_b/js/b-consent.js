// =============================================================
// b-consent.js — E30 동의 확인 모달 (할 일 12)
//   정본: 동의 확인은 서미란에게 증거를 제시하는 과정에서 시작합니다.
//   서버가 대화 응답에 "동의 요청 신호"를 넣어 주면 이 모달을 띄웁니다.
//
//   ※ 그 신호와 동의 API는 아직 백엔드에 없습니다.
//     신호 필드 이름은 b-config.js의 CONSENT_FLAG에서 바꿉니다.
//     조건 검증과 결과는 모두 서버가 정합니다.
// =============================================================
window.B = window.B || {};

B.consent = (function () {
  var esc = B.esc, $ = B.$;

  // 대화 응답(raw)에 신호가 있으면 모달을 엽니다.
  function check(raw) {
    var req = raw && raw[B.config.CONSENT_FLAG];
    if (req) open(req);
  }

  function open(req) {
    B.openModal(req.title || '동의 확인',
      '<p>' + esc(req.text || '') + '</p>' +
      '<div class="b-tile-actions"><button type="button" id="b-consent-no">취소</button>' +
      '<button type="button" id="b-consent-yes" class="b-primary">동의 확인 요청</button></div>', true);
    $('b-consent-yes').onclick = function () { answer(true); };
    $('b-consent-no').onclick = function () { answer(false); };
  }

  function answer(accepted) {
    B.api.consent(accepted).then(function (r) {
      B.closeModal();
      B.toast((r && r.message) || '응답을 보냈습니다');
      if (B.events) B.events.check();
    }).catch(function (e) {
      B.closeModal();
      B.toast(e.message);
    });
  }

  return { check: check, open: open };
})();
