// =============================================================
// dev/b-mock.js — 개발용 모의 응답 (배포 화면에서 불러오지 않음)
//   예시 데이터일 뿐 실제 사건 내용·정답·해금 규칙과 무관합니다.
//   demo.html에서만 불러옵니다. Django 실제 템플릿에는 넣지 마세요.
// =============================================================
window.B = window.B || {};

(function () {
  var C = B.config;
  // ---------------------------------------------------------
  // 2. 모의 응답 (서버 없이 화면 확인용)
  //    예시 데이터일 뿐 실제 사건 내용·해금 규칙과 무관합니다.
  // ---------------------------------------------------------
  function wait(v) { return new Promise(function (ok) { setTimeout(function () { ok(JSON.parse(JSON.stringify(v))); }, 150); }); }

  var M = {
    game: {
      sessionId: 'mock-session', phase: 'INVESTIGATION', currentChapter: 'CH01 · 예시',
      unlockedChapters: ['CH01'], activeCharacterId: '', unlockedCharacters: ['C01', 'C03', 'C05'],
      collection: { score: 0, total: 0 }, canAccuse: false, attemptsLeft: 3, outcome: null,
      revision: 1, events: []
    },
    evidence: [
      { evidenceId: 'E01', name: '예시 증거 1', score: 0, stage: 'collected' },
      { evidenceId: 'E02', name: '예시 증거 2', score: 0, stage: 'collected' }
    ],
    history: {},
    events: [],
    eventSerial: 0
  };
  function bump() { M.game.revision += 1; }

  B.mock = {
    createGame: function () { return wait(M.game); },
    getGame: function () { return wait(M.game); },
    completePrologue: function () { return wait(M.game); },
    select: function (id) { M.game.activeCharacterId = id; bump(); return wait(M.game); },
    chatHistory: function (id) { return wait(M.history[id] || []); },
    chat: function (question, evidenceId) {
      var id = M.game.activeCharacterId;
      var reply = '[예시 답변] ' + (evidenceId ? '제시한 자료(' + evidenceId + ')를 확인했습니다.' : '질문을 확인했습니다.') +
        ' 실제 답변은 서버에서 받습니다.';
      (M.history[id] = M.history[id] || []).push({ userMessage: question, displayText: reply });
      bump();
      var raw = { characterId: id, display_text: reply, game: M.game };
      // 동의 모달 시험용: 질문에 "동의"를 넣으면 신호가 옵니다(모의 응답 전용).
      if (question.indexOf('동의') >= 0) {
        raw[C.CONSENT_FLAG] = { title: '동의 확인(예시)', text: '예시 문장입니다. 실제 문장과 조건은 서버가 보냅니다.' };
      }
      return wait({ reply: reply, game: M.game, raw: raw });
    },
    evidenceList: function () { return wait({ items: M.evidence, collectedCount: M.evidence.length, totalCount: M.evidence.length }); },
    evidenceDetail: function (id) {
      return wait({
        id: id, title: '예시 증거 ' + id.slice(-1), body: '가상의 UI 테스트 문서입니다. 실제 사건 내용이 아닙니다.',
        holderId: '', acquiredBy: 'initial', confirmedRelations: [],
        documents: [
          { id: id + '-1', label: '문서 1', title: '예시 문서 1', body: '첫 번째 예시 문서 내용입니다.' },
          { id: id + '-2', label: '문서 2', title: '예시 문서 2', body: '두 번째 예시 문서 내용입니다.' }
        ]
      });
    },
    evidencePhotoUrl: function () { return ''; },
    relationships: function () {
      var ids = M.game.unlockedCharacters;
      var edges = ids.length >= 2 ? [{ id: 'r1', sourceId: ids[0], targetId: ids[1], relation: '예시 관계' }] : [];
      return wait({ nodes: ids.map(function (i) { return { id: i, label: B.personName(i) }; }), edges: edges });
    },
    pendingEvents: function () { return wait(M.events); },
    ackEvent: function (key) {
      M.events = M.events.filter(function (e) { return e.eventKey !== key; });
      return wait({ eventKey: key, acknowledged: true, created: true, revision: M.game.revision });
    },
    accuse: function (suspectId) {
      M.game.attemptsLeft = Math.max(0, M.game.attemptsLeft - 1);
      bump();
      var result = M.game.attemptsLeft === 0 ? 'INCORRECT' : 'NOT_ENOUGH_EVIDENCE';
      if (M.game.attemptsLeft === 0) { M.game.phase = 'FINISHED'; M.game.outcome = 'FAILURE'; }
      return wait({ result: result, attemptsLeft: M.game.attemptsLeft, game: M.game });
    },
    ending: function () {
      return wait({ outcome: M.game.outcome || 'FAILURE', title: '엔딩 제목(예시)', message: '엔딩 문장은 서버가 보냅니다(예시).',
        deepEligible: false, truth: null, game: M.game });
    },
    consent: function (accepted) {
      return wait({ message: accepted ? '예시: 동의 응답을 보냈습니다.' : '예시: 취소했습니다.' });
    },

    // ---- 모의 응답 전용 시험 버튼 ----
    _unlockAll: function () {
      M.game.unlockedCharacters = Object.keys(B.roster);
      M.game.canAccuse = true; M.game.currentChapter = 'CH04 · 예시';
      M.evidence.push({ evidenceId: 'E03', name: '예시 증거 3', score: 0, stage: 'collected' });
      bump(); return wait(M.game);
    },
    _pushEvent: function () {
      M.eventSerial += 1;
      M.events.push({ eventKey: 'mock-event-' + M.eventSerial, chapter: 'CH01', title: '새로운 수사 알림(예시)',
        text: '예시 알림 ' + M.eventSerial + '입니다. 실제 문장은 서버가 보냅니다.' });
      return wait(true);
    }
  };

})();
