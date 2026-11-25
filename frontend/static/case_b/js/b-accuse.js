// =============================================================
// b-accuse.js — 최종 추리 (할 일 9)
//   인물 1명을 고르고 확인 → POST /accusations
//   맞았는지·엔딩은 서버가 판정합니다. 프론트는 결과만 보여 줍니다.
// =============================================================
window.B = window.B || {};

B.accuse = (function () {
  var S = B.store, esc = B.esc, $ = B.$;

  // 고발 버튼은 서버가 canAccuse=true를 줄 때만 보입니다.
  function syncButton() {
    var btn = $('b-accuse-btn');
    if (btn) btn.hidden = !S.game.canAccuse;
  }

  function open() {
    if (!S.game.canAccuse) { B.toast('아직 최종 추리를 할 수 없습니다'); return; }
    var ids = S.game.characters;
    B.openModal('최종 추리',
      '<p>범인이라고 생각하는 인물 1명을 고르세요. 남은 기회: <b>' + S.game.attemptsLeft + '</b>번</p>' +
      '<div class="b-suspects">' + ids.map(function (id) {
        return '<label class="b-suspect"><input type="radio" name="b-suspect" value="' + esc(id) + '">' +
          '<img src="' + esc(B.personImage(id)) + '" alt="" onerror="this.style.display=\'none\'">' +
          '<span>' + esc(B.personName(id)) + '</span></label>';
      }).join('') + '</div>' +
      '<button type="button" id="b-accuse-next" class="b-primary" disabled>이 인물로 지목</button>');
    document.querySelectorAll('input[name="b-suspect"]').forEach(function (r) {
      r.onchange = function () { $('b-accuse-next').disabled = false; };
    });
    $('b-accuse-next').onclick = function () {
      var picked = document.querySelector('input[name="b-suspect"]:checked');
      if (picked) confirmStep(picked.value);
    };
  }

  // 한 번 더 확인합니다(기회가 줄어들기 때문).
  function confirmStep(id) {
    B.openModal('지목 확인',
      '<p><b>' + esc(B.personName(id)) + '</b>을(를) 범인으로 지목합니다.</p>' +
      '<p class="b-muted">지목하면 기회가 1번 줄어듭니다.</p>' +
      '<div class="b-tile-actions"><button type="button" id="b-accuse-back">다시 고르기</button>' +
      '<button type="button" id="b-accuse-go" class="b-primary">지목하기</button></div>');
    $('b-accuse-back').onclick = open;
    $('b-accuse-go').onclick = function () { submit(id); };
  }

  function submit(id) {
    $('b-accuse-go').disabled = true;
    B.api.accuse(id).then(function (r) {
      S.setGame(r.game);
      // 게임이 끝났으면 엔딩으로
      if (r.game && (r.game.phase === 'FINISHED' || r.game.outcome)) {
        B.closeModal();
        if (B.ending) B.ending.show();
        return;
      }
      var text = {
        CORRECT: '지목이 받아들여졌습니다.',
        INCORRECT: '지목이 맞지 않습니다.',
        NOT_ENOUGH_EVIDENCE: '단서가 더 필요합니다.'
      }[r.result] || '판정 결과를 받았습니다.';
      B.openModal('판정', '<p>' + esc(text) + '</p><p class="b-muted">남은 기회: ' + r.attemptsLeft + '번</p>' +
        '<button type="button" id="b-accuse-close">수사로 돌아가기</button>');
      $('b-accuse-close').onclick = B.closeModal;
    }).catch(function (e) {
      B.toast(e.message);
      if ($('b-accuse-go')) $('b-accuse-go').disabled = false;
    });
  }

  S.on(syncButton);
  return { open: open, syncButton: syncButton };
})();
