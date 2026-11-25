// =============================================================
// b-records.js — 수사 기록 (할 일 8)
//   탭: 대화 기록 / 저장한 진술 / 수사 노트 (+ 타임라인: 설정으로 켜고 끔)
//   진술·노트는 브라우저에만 저장하고 서버로 보내지 않습니다.
// =============================================================
window.B = window.B || {};

B.records = (function () {
  var S = B.store, esc = B.esc, $ = B.$;
  var current = 'chat';

  function tabs() {
    var list = [['chat', '대화 기록'], ['pins', '저장한 진술'], ['note', '수사 노트']];
    if (B.config.SHOW_TIMELINE) list.splice(2, 0, ['timeline', '타임라인']);
    return list;
  }

  function open(tab) {
    current = tab || current;
    B.openModal('수사 기록',
      '<div class="b-tabs">' + tabs().map(function (t) {
        return '<button type="button" data-b-record="' + t[0] + '" class="' + (current === t[0] ? 'active' : '') + '">' + t[1] + '</button>';
      }).join('') + '</div><div id="b-record-body" class="b-record-body"></div>');
    show(current);
  }

  function show(tab) {
    current = tab;
    document.querySelectorAll('[data-b-record]').forEach(function (b) {
      b.classList.toggle('active', b.dataset.bRecord === tab);
    });
    var body = $('b-record-body');
    if (!body) return;

    if (tab === 'chat') {
      var ids = Object.keys(S.logs).filter(function (id) { return (S.logs[id] || []).length; });
      body.innerHTML = ids.length ? ids.map(function (id) {
        return '<h4>' + esc(B.personName(id)) + '</h4>' + S.logs[id].map(function (m) {
          return '<p class="b-line"><b>' + esc(m.from) + '</b> ' + esc(m.text) + '</p>';
        }).join('');
      }).join('') : '<p class="b-muted">아직 대화 기록이 없습니다.</p>';
    }

    if (tab === 'pins') {
      var pins = S.load('pins', []);
      body.innerHTML = pins.length ? pins.map(function (p, i) {
        return '<div class="b-tile"><b>' + esc(p.from) + '</b><p>' + esc(p.text) + '</p>' +
          '<small class="b-muted">진술, 미검증</small> ' +
          '<button type="button" data-b-unpin="' + i + '">삭제</button></div>';
      }).join('') : '<p class="b-muted">저장한 진술이 없습니다. 면담 중 인물 대사의 "진술 저장"을 누르세요.</p>';
    }

    if (tab === 'timeline') {
      // 서버 타임라인 API가 없어 저장한 진술을 저장한 순서대로만 보여 줍니다(팀 결정 전 임시).
      var t = S.load('pins', []);
      body.innerHTML = t.length ? t.map(function (p) {
        return '<p class="b-line"><b>' + esc(p.from) + '</b> ' + esc(p.text) + '</p>';
      }).join('') : '<p class="b-muted">공개된 타임라인이 없습니다.</p>';
    }

    if (tab === 'note') {
      body.innerHTML = '<textarea id="b-note" placeholder="자유롭게 적어 두세요. 이 브라우저에만 저장됩니다.">' +
        esc(S.load('note', '')) + '</textarea><small class="b-muted" id="b-note-state">자동 저장</small>';
      var timer;
      $('b-note').oninput = function (e) {
        clearTimeout(timer);
        timer = setTimeout(function () { S.save('note', e.target.value); $('b-note-state').textContent = '저장됨'; }, 400);
      };
    }
  }

  function unpin(i) {
    var pins = S.load('pins', []);
    pins.splice(i, 1);
    S.save('pins', pins);
    show('pins');
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.bRecord) show(b.dataset.bRecord);
    if (b.dataset.bUnpin !== undefined) unpin(+b.dataset.bUnpin);
  });

  return { open: open };
})();
