
 // common/store.js
// 공통 게임 상태 관리 (A 최초 작성, A·B 공용)

window.CASE = window.CASE || {};

CASE.store = (function () {

    // 1. 초기 상태
    const initialState = {
        gameState: null,
        currentScreen: 'investigation',
        currentLocation: null,
        selectedNpc: null,
        isLoading: false,
        error: null
    };

    // 2. 현재 상태 및 구독자 관리
    let state = structuredClone(initialState);
    const listeners = new Set();

    // 3. 현재 상태 조회
    function getState() {
        return structuredClone(state);
    }

    // 4. 상태 변경 알림
    function notify() {
        listeners.forEach(function (listener) {
            try {
                listener(getState());
            } catch (error) {
                console.error('상태 구독 처리 오류:', error);
            }
        });
    }

    // 5. 공통 상태 갱신
    function setState(newState) {
        state = {
            ...state,
            ...structuredClone(newState)
        };

        notify();
    }

    // 6. 서버에서 받은 게임 상태 반영
    function setGameState(gameState) {
        setState({ gameState: gameState });
    }

    // 7. 상태 변경 구독 및 구독 해제
    function subscribe(listener) {
        listeners.add(listener);

        return function () {
            listeners.delete(listener);
        };
    }

    // 8. 상태 초기화
    function resetState() {
        state = structuredClone(initialState);
        notify();
    }

    // 9. 외부 파일에서 사용할 공통 함수
    return {
        getState: getState,
        setState: setState,
        setGameState: setGameState,
        subscribe: subscribe,
        resetState: resetState
    };

})();
