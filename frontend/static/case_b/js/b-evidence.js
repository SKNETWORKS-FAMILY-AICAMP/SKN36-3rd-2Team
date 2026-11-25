// =============================================================
// b-evidence.js — 증거함 (할 일 4·5, 6의 시작점)
//   4. 증거함: 서버가 준 개수만큼 카드로 표시, 누르면 상세(사진·본문·문서 탭)
//   5. 나란히 보기: 2개까지 골라 좌우 비교 (차이 강조 없음)
//   6. "한 개 제시" → 면담실 입력창 위에 표시 (b-interview.js의 choose)
//
// 화면에 점수(score)는 절대 보여 주지 않습니다(스포일러 원칙).
// 증거 사진은 서버 주소로만 불러옵니다. 공개 폴더에 증거 이미지를 두지 않습니다.
// =============================================================
window.B = window.B || {};

B.evidence = (function () {
  var S = B.store, esc = B.esc, $ = B.$;

  // 서버에서 증거 목록을 다시 받아옵니다.
  function refresh() {
    return B.api.evidenceList().then(function (r) {
      S.setEvidence(r.items);
      return r;
    }).catch(function (e) { B.toast(e.message); });
  }

  function photo(id) {
    var url = B.api.evidencePhotoUrl(id);
    if (!url) return '<div class="b-photo none">이미지 없음</div>';
    // 사진이 없거나 권한이 없으면 칸을 숨깁니다.
    return '<img class="b-photo" src="' + esc(url) + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
  }

  // ---- 4. 증거함 목록 ----
  function open() {
    refresh().then(draw);
  }

  function draw() {
    var list = S.evidence;
    var cards = list.map(function (e) {
      var picked = S.compare.indexOf(e.id) >= 0;
      return '<div class="b-tile">' +
        photo(e.id) +
        '<b>' + esc(e.title) + '</b>' +
        '<div class="b-tile-actions">' +
        '<button type="button" data-b-detail="' + esc(e.id) + '">자세히</button>' +
        '<button type="button" data-b-compare="' + esc(e.id) + '">' + (picked ? '비교 해제' : '비교 선택') + '</button>' +
        '<button type="button" data-b-present="' + esc(e.id) + '">한 개 제시</button>' +
        '</div></div>';
    }).join('');

    B.openModal('증거함 · ' + list.length + '개',
      (list.length ? '<div class="b-grid">' + cards + '</div>' : '<p class="b-muted">획득한 증거가 없습니다.</p>') +
      '<p class="b-muted b-help">비교는 2개까지 고를 수 있습니다. 인물에게는 한 번에 1개만 제시합니다.</p>' +
      (S.compare.length === 2 ? '<button type="button" id="b-open-compare" class="b-primary">나란히 보기 (2개)</button>' :
        '<span class="b-muted">비교 선택 ' + S.compare.length + '/2</span>'));
    if ($('b-open-compare')) $('b-open-compare').onclick = openCompare;
  }

  // ---- 4. 상세 보기 ----
  // showAll = true 이면 탭 없이 문서를 모두 펼칩니다(나란히 보기용).
  function detailHtml(d, showAll) {
    var docs = d.documents || [];
    if (showAll) {
      return photo(d.id) + (d.body ? '<p class="b-body">' + esc(d.body) + '</p>' : '') +
        docs.map(function (doc) {
          return '<div class="b-doc"><b>' + esc(doc.title) + '</b><p>' + esc(doc.body) + '</p></div>';
        }).join('');
    }
    var tabs = docs.length > 1 ?'<div class="b-tabs">' + docs.map(function (doc, i) {
      return '<button type="button" class="' + (i === 0 ? 'active' : '') + '" data-b-doc="' + i + '">' + esc(doc.label || ('문서 ' + (i + 1))) + '</button>';
    }).join('') + '</div>' : '';
    var first = docs[0];
    return photo(d.id) +
      (d.body ? '<p class="b-body">' + esc(d.body) + '</p>' : '') +
      tabs +
      (first ? '<div class="b-doc" id="b-doc"><b>' + esc(first.title) + '</b><p>' + esc(first.body) + '</p></div>' : '');
  }

  function openDetail(id) {
    B.api.evidenceDetail(id).then(function (d) {
      B.openModal(d.title || '증거',
        detailHtml(d) +
        '<div class="b-tile-actions"><button type="button" id="b-back-box">← 증거함</button>' +
        '<button type="button" data-b-present="' + esc(id) + '">한 개 제시</button></div>');
      $('b-back-box').onclick = draw;
      bindDocTabs(d);
    }).catch(function (e) { B.toast(e.message); });
  }

  function bindDocTabs(d) {
    var docs = d.documents || [];
    document.querySelectorAll('[data-b-doc]').forEach(function (btn) {
      btn.onclick = function () {
        var doc = docs[+btn.dataset.bDoc];
        document.querySelectorAll('[data-b-doc]').forEach(function (x) { x.classList.remove('active'); });
        btn.classList.add('active');
        $('b-doc').innerHTML = '<b>' + esc(doc.title) + '</b><p>' + esc(doc.body) + '</p>';
      };
    });
  }

  // ---- 5. 나란히 보기 ----
  function toggleCompare(id) {
    var i = S.compare.indexOf(id);
    if (i >= 0) S.compare.splice(i, 1);
    else S.compare = S.compare.concat(id).slice(-2);   // 3번째를 고르면 가장 먼저 고른 것이 빠짐
    draw();
  }

  function openCompare() {
    Promise.all(S.compare.map(function (id) { return B.api.evidenceDetail(id); })).then(function (ds) {
      B.openModal('나란히 보기',
        '<div class="b-split">' + ds.map(function (d) {
          return '<div class="b-tile"><b>' + esc(d.title) + '</b>' + detailHtml(d, true) + '</div>';
        }).join('') + '</div>' +
        '<button type="button" id="b-back-box">← 증거함</button>');
      $('b-back-box').onclick = draw;
    }).catch(function (e) { B.toast(e.message); });
  }

  // ---- 6. 한 개 제시 ----
  function present(id) {
    if (B.interview && B.interview.choose(id)) {
      B.closeModal();
      B.toast('증거 1개 선택 · 전송하면 제시됩니다');
    }
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.bDetail) openDetail(b.dataset.bDetail);
    if (b.dataset.bCompare) toggleCompare(b.dataset.bCompare);
    if (b.dataset.bPresent) present(b.dataset.bPresent);
  });

  return { open: open, refresh: refresh };
})();
