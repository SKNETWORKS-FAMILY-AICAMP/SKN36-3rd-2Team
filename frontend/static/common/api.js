// =============================================================
// common/api.js — 공통 서버 요청 골격 (B 최초 작성, A·B 공용)
//
// 여기에는 "요청을 보내는 방법"만 둡니다. 어떤 경로를 부를지는
// A는 case_a/, B는 case_b/ 의 각자 파일에서 CASE.api.request()로 부릅니다.
//
// 통일 규칙
//   - 쿠키:   모든 요청에 credentials: 'include' (게임 세션 주인 쿠키)
//   - 시간:   일반 15초, 대화 같은 긴 요청은 호출하는 쪽이 timeoutMs를 넘김
//   - 오류:   서버의 message/detail 문구를 그대로 Error로 던짐 → 화면은 알림으로 표시
//   - 재시도: 자동 재시도하지 않음(상태 변경 요청이 두 번 갈 수 있음). 사용자가 다시 누름
//   - 중복:   CASE.api.once(key, fn)으로 같은 요청이 끝나기 전 다시 보내지 않게 막음
//
// 서버 주소(base)는 실제 포트·CORS가 확정되면 이 줄만 바꿉니다.
// =============================================================
window.CASE = window.CASE || {};

CASE.api = (function () {
  var base = 'http://localhost:8000/api';   // FastAPI 주소(미확정). 페이지와 같은 호스트 이름(localhost)으로 맞출 것
  var TIMEOUT_MS = 15000;
  var pending = {};

  function request(path, options, timeoutMs) {
    options = options || {};
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs || TIMEOUT_MS);

    return fetch(base + path, {
      method: options.method || 'GET',
      headers: options.body ? { 'Content-Type': 'application/json' } : {},
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: 'include',
      signal: controller.signal
    }).then(function (res) {
      clearTimeout(timer);
      if (res.ok) return res.json();
      return res.json().catch(function () { return {}; }).then(function (body) {
        var msg = body && (body.message || body.detail);
        var err = new Error(typeof msg === 'string' ? msg : '요청에 실패했습니다 (' + res.status + ')');
        err.status = res.status;          // 401/403/404면 세션 문제일 수 있음(복구 규칙은 공동 결정)
        throw err;
      });
    }, function (err) {
      clearTimeout(timer);
      if (err && err.name === 'AbortError') throw new Error('서버 응답 시간이 초과되었습니다. 다시 시도해 주세요.');
      throw new Error('서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.');
    });
  }

  // 같은 key의 요청이 진행 중이면 그 요청을 그대로 돌려줍니다(중복 클릭 방지).
  function once(key, fn) {
    if (pending[key]) return pending[key];
    pending[key] = Promise.resolve().then(fn).finally(function () { delete pending[key]; });
    return pending[key];
  }

  return {
    request: request,
    once: once,
    getBase: function () { return base; },
    setBase: function (url) { base = url; }
  };
})();
