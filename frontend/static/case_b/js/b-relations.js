// =============================================================
// b-relations.js — 인물관계도 (할 일 7)
//   서버(GET /relationships)가 준 인물과 관계선만 그립니다.
//   누가 나오고 어떤 관계가 보일지는 서버가 정합니다.
// =============================================================
window.B = window.B || {};

B.relations = (function () {
  var esc = B.esc;

  function open() {
    B.api.relationships().then(draw).catch(function (e) { B.toast(e.message); });
  }

  function draw(data) {
    var nodes = data.nodes || [], edges = data.edges || [];
    if (!nodes.length) {
      B.openModal('인물관계도', '<p class="b-muted">만난 인물과 공개된 관계가 여기에 표시됩니다.</p>');
      return;
    }
    // 인물을 원 모양으로 배치합니다.
    var W = 600, H = 460, cx = W / 2, cy = H / 2 - 10, R = Math.min(210, 70 + nodes.length * 16);
    var pos = {};
    nodes.forEach(function (n, i) {
      var a = -Math.PI / 2 + i * 2 * Math.PI / nodes.length;
      pos[n.id] = { x: cx + R * Math.cos(a), y: cy + R * 0.8 * Math.sin(a) };
    });

    var lines = edges.map(function (e) {
      var a = pos[e.sourceId], b = pos[e.targetId];
      if (!a || !b) return '';
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      return '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" class="b-edge"/>' +
        '<text x="' + mx + '" y="' + (my - 4) + '" class="b-edge-label" text-anchor="middle">' + esc(e.relation) + '</text>';
    }).join('');

    var dots = nodes.map(function (n) {
      var p = pos[n.id], clip = 'clip-' + esc(n.id);
      var hasImg = !!B.roster[n.id];
      return '<g class="b-node">' +
        '<clipPath id="' + clip + '"><circle cx="' + p.x + '" cy="' + p.y + '" r="28"/></clipPath>' +
        '<circle cx="' + p.x + '" cy="' + p.y + '" r="30" class="b-node-ring"/>' +
        (hasImg ? '<image href="' + esc(B.personImage(n.id)) + '" x="' + (p.x - 28) + '" y="' + (p.y - 34) + '" width="56" height="70" clip-path="url(#' + clip + ')" preserveAspectRatio="xMidYMin slice"/>' : '') +
        '<text x="' + p.x + '" y="' + (p.y + 48) + '" text-anchor="middle" class="b-node-label">' + esc(n.label || B.personName(n.id)) + '</text>' +
        '</g>';
    }).join('');

    B.openModal('인물관계도',
      '<svg class="b-graph" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="인물관계도">' + lines + dots + '</svg>' +
      '<p class="b-muted b-help">서버가 공개한 인물과 관계만 표시합니다.</p>');
  }

  return { open: open };
})();
