// =============================================================
// b-store.js — 화면이 기억하는 값(상태)을 모아 두는 곳
//
// 1) 서버에서 받은 값: game (챕터, 공개 인물, 고발 가능 여부 등)
//    → 서버 응답이 올 때마다 B.store.setGame()으로만 바꿉니다.
// 2) 화면에서만 쓰는 값: 지금 면담 중인 인물, 선택한 증거 등
// 3) 브라우저에 저장하는 값: 저장한 진술, 수사 노트, 이미 본 알림
//    → 서버로 보내지 않습니다.
//
// 값이 바뀌면 B.store.emit()을 부르고, 화면들은 B.store.on()으로 다시 그립니다.
// =============================================================
window.B = window.B || {};

B.store = {
  // ---- 서버에서 받은 값 ----
  game: {
    sessionId: null,
    phase: null,            // PROLOGUE / INVESTIGATION / ACCUSATION / FINISHED
    chapter: '',            // currentChapter
    characters: [],         // unlockedCharacters (인물 ID 목록)
    activeCharacterId: null,
    canAccuse: false,
    attemptsLeft: 0,
    outcome: null,
    revision: 0
  },
  evidence: [],             // [{ id, title, stage }]  (점수는 일부러 저장하지 않음)

  // ---- 화면에서만 쓰는 값 ----
  who: null,                // 지금 면담 중인 인물 ID
  logs: {},                 // { 인물ID: [{ from, text, npc }] }
  selectedEvidence: null,   // 다음 질문과 함께 제시할 증거 ID (1개)
  compare: [],              // 나란히 보기로 고른 증거 ID (최대 2개)

  // 서버 GameResponse를 화면용 모양으로 바꿔 저장합니다.
  setGame: function (g) {
    if (!g) return;
    this.game = {
      sessionId: g.sessionId,
      phase: g.phase,
      chapter: g.currentChapter || '',
      characters: g.unlockedCharacters || [],
      activeCharacterId: g.activeCharacterId || null,
      canAccuse: !!g.canAccuse,
      attemptsLeft: g.attemptsLeft || 0,
      outcome: g.outcome || null,
      revision: g.revision || 0
    };
    // 공개 목록에서 빠진 인물과 면담 중이면 비웁니다.
    if (this.who && this.game.characters.indexOf(this.who) < 0) {
      this.who = null;
      this.selectedEvidence = null;
    }
    this.emit();
  },

  // 서버 증거 목록을 화면용 모양으로 저장합니다.
  setEvidence: function (items) {
    this.evidence = (items || []).map(function (e) {
      return { id: e.evidenceId, title: e.name, stage: e.stage };
    });
    var ids = this.evidence.map(function (e) { return e.id; });
    this.compare = this.compare.filter(function (id) { return ids.indexOf(id) >= 0; });
    if (this.selectedEvidence && ids.indexOf(this.selectedEvidence) < 0) this.selectedEvidence = null;
    this.emit();
  },

  // ---- 브라우저 저장(localStorage) ----
  key: function (name) {
    return B.config.STORAGE_PREFIX + (this.game.sessionId || 'local') + ':' + name;
  },
  load: function (name, fallback) {
    try {
      var raw = localStorage.getItem(this.key(name));
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }   // 저장소를 못 쓰는 환경에서도 멈추지 않게
  },
  save: function (name, value) {
    try { localStorage.setItem(this.key(name), JSON.stringify(value)); } catch (e) { /* 무시 */ }
  },

  // ---- 바뀜 알림 ----
  listeners: [],
  on: function (fn) { this.listeners.push(fn); },
  emit: function () {
    this.listeners.forEach(function (fn) {
      try { fn(); } catch (e) { console.error(e); }
    });
  }
};
