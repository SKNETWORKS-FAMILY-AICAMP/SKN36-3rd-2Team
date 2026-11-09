"""Issue #65 - 같은 세션 동시 대화 차단 테스트."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from crimescene.trigger.dialogue_lock import exclusive_per_session


def test_same_session_cannot_run_twice() -> None:
    started = Event()
    release = Event()

    @exclusive_per_session
    def run(*, session_id: str) -> str:
        started.set()
        assert release.wait(timeout=3)
        return session_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, session_id="case-1")
        assert started.wait(timeout=2)
        with pytest.raises(ValueError, match="이전 대화"):
            run(session_id="case-1")
        release.set()
        assert first.result(timeout=3) == "case-1"


def test_different_session_can_run() -> None:
    @exclusive_per_session
    def run(*, session_id: str) -> str:
        return session_id

    assert run(session_id="case-2") == "case-2"
    assert run(session_id="case-3") == "case-3"


def test_lock_released_after_error() -> None:
    calls = 0

    @exclusive_per_session
    def run(*, session_id: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("test failure")
        return session_id

    with pytest.raises(RuntimeError):
        run(session_id="case-4")
    assert run(session_id="case-4") == "case-4"
