// =============================================================
// b-api.js — B 기능의 서버 요청 (면담·증거·관계도·알림·추리·엔딩)
//
// 요청 방법(쿠키·시간·오류)은 공통 파일 common/api.js의 CASE.api.request를 씁니다.
// 여기에는 B가 부르는 경로만 있습니다.
// 경로와 필드 이름은 저장소 dev(6d4ec11)의 FastAPI 코드에서 확인했습니다.
//   backend/src/crimescene/api/app.py, story_event_http.py
//
// 모의 응답은 dev/b-mock.js에 따로 있습니다. 배포 화면에서는 그 파일을 불러오지 않습니다.
// =============================================================
window.B = window.B || {};

(function () {
  var C = B.config;
  function request(path, options, timeoutMs) { return CASE.api.request(path, options, timeoutMs); }

  function game(path) {
    return '/games/' + encodeURIComponent(B.store.game.sessionId) + path;
  }

  var real = {
    // 새 게임. 서버는 본문이 없어야 받습니다.
    createGame: function () { return request('/games', { method: 'POST' }); },
    getGame: function () { return request(game('')); },
    // 프롤로그 끝 → 조사 단계(INVESTIGATION). 본문 없음.
    // 실제 화면에서는 A의 오프닝이 끝날 때 부릅니다. B 데모는 시작할 때 부릅니다.
    completePrologue: function () { return request(game('/prologue/complete'), { method: 'POST' }); },

    // 면담할 인물을 서버에 알림. 대화(chat)는 이 인물에게 갑니다.
    select: function (characterId) {
      return request(game('/characters/' + encodeURIComponent(characterId) + '/select'), { method: 'POST' });
    },
    // 이전 대화 → [{ userMessage, displayText }]
    chatHistory: function (characterId) {
      return request(game('/chats/' + encodeURIComponent(characterId))).then(function (r) { return r.messages || []; });
    },
    // 질문 + 증거 1개(없으면 null) → { reply, game, raw }
    chat: function (question, evidenceId) {
      return request(game('/chat'), {
        method: 'POST',
        body: { question: question, presentedEvidenceId: evidenceId || null }
      }, C.CHAT_TIMEOUT_MS).then(function (r) {
        return { reply: r.display_text, game: r.game, raw: r };
      });
    },

    // 증거함 → { items:[{evidenceId,name,score,stage}], collectedCount, totalCount }
    evidenceList: function () { return request(game('/evidence')); },
    // 증거 상세 → { id, title, body, holderId, acquiredBy, confirmedRelations, documents }
    evidenceDetail: function (id) { return request(game('/evidence/' + encodeURIComponent(id))); },
    // 증거 사진 주소(<img src>에 그대로 넣음). 서버가 획득 여부를 확인합니다.
    evidencePhotoUrl: function (id) { return CASE.api.getBase() + game('/evidence/' + encodeURIComponent(id) + '/photo'); },

    // 관계도 → { nodes:[{id,label}], edges:[{id,sourceId,targetId,relation}] }
    relationships: function () { return request(game('/relationships')); },

    // 새 수사 알림 → [{ eventKey, chapter, title, text }]
    pendingEvents: function () {
      return request(game('/story-events/pending')).then(function (r) { return r.items || []; });
    },
    // 알림 확인. 본문 없음. 같은 알림을 두 번 보내도 서버가 안전하게 처리합니다.
    ackEvent: function (eventKey) {
      return request(game('/story-events/' + encodeURIComponent(eventKey) + '/ack'), { method: 'POST' });
    },

    // 최종 추리: 인물 1명 → { result, attemptsLeft, game }
    accuse: function (suspectId) {
      return request(game('/accusations'), {
        method: 'POST',
        body: { suspectId: suspectId, expectedRevision: B.store.game.revision }
      });
    },
    // 엔딩 → { outcome, title, message, deepEligible, truth, game }
    ending: function () { return request(game('/ending')); },

    // E30 동의 응답: 서버 API가 아직 없습니다.
    consent: function () {
      return Promise.reject(new Error('동의 확인 API가 아직 없습니다(백엔드 협의 필요).'));
    }
  };

  // ---------------------------------------------------------
  // 화면이 쓰는 입구: B.api.이름(...)
  //   USE_MOCK이 true이고 dev/b-mock.js가 불러와져 있으면 모의 응답, 아니면 실제 서버
  // ---------------------------------------------------------
  B.api = {};
  Object.keys(real).forEach(function (name) {
    B.api[name] = function () {
      var target = (C.USE_MOCK && B.mock) ? B.mock : real;
      return target[name].apply(null, arguments);
    };
  });
})();
