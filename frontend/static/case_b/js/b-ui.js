// =============================================================
// b-ui.js — 여러 화면이 같이 쓰는 작은 도구
//   B.$(id)        : id로 요소 찾기
//   B.esc(text)    : 글자를 HTML에 안전하게 넣기(꼭 써야 함)
//   B.openModal()  : 가운데 창 열기 / B.closeModal() : 닫기
//   B.toast(text)  : 아래쪽에 잠깐 뜨는 알림
// A 담당 화면과 겹치면 공통 파일로 합칠지 A와 상의하세요.
// =============================================================
window.B = window.B || {};

B.$ = function (id) { return document.getElementById(id); };

// 서버나 사용자가 보낸 글자는 반드시 이 함수를 거쳐 화면에 넣습니다.
B.esc = function (value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
};

// 모달(가운데 창)이 페이지에 없으면 만들어 둡니다.
B.ensureModal = function () {
  if (B.$('b-modal')) return;
  var wrap = document.createElement('div');
  wrap.innerHTML =
    '<div class="b-modal" id="b-modal" hidden>' +
    '  <section class="b-card" role="dialog" aria-modal="true" aria-labelledby="b-modal-title">' +
    '    <div class="b-card-head"><h2 id="b-modal-title"></h2>' +
    '      <button type="button" id="b-modal-close">닫기 ✕</button></div>' +
    '    <div id="b-modal-body"></div>' +
    '  </section>' +
    '</div>' +
    '<div class="b-toast" id="b-toast" hidden></div>';
  document.body.appendChild(wrap);
  B.$('b-modal-close').onclick = function () { B.closeModal(); };
  B.$('b-modal').addEventListener('click', function (e) {
    if (e.target.id === 'b-modal' && !B.modalLocked) B.closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !B.modalLocked) B.closeModal();
  });
};

// locked = true 이면 바깥 클릭·Esc·닫기 버튼으로 닫히지 않습니다(알림 확인용).
B.openModal = function (title, html, locked) {
  B.ensureModal();
  B.modalLocked = !!locked;
  B.$('b-modal-title').textContent = title;
  B.$('b-modal-body').innerHTML = html;
  B.$('b-modal-close').hidden = !!locked;
  B.$('b-modal').hidden = false;
};

B.closeModal = function () {
  if (!B.$('b-modal')) return;
  B.modalLocked = false;
  B.$('b-modal').hidden = true;
  B.$('b-modal-body').innerHTML = '';
};

var toastTimer = null;
B.toast = function (text) {
  B.ensureModal();
  var t = B.$('b-toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { t.hidden = true; }, 2600);
};
