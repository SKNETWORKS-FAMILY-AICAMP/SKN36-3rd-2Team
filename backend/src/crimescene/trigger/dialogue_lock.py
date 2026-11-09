"""동일 프로세스 내 동일 세션 NPC 대화 중복 실행 방지."""

from functools import wraps
from threading import Lock
from weakref import WeakValueDictionary

_registry_lock = Lock()
_session_locks: WeakValueDictionary[str, Lock] = WeakValueDictionary()


def exclusive_per_session(func):
    """같은 세션에서 동시 대화 생성 시 즉시 거부합니다.

    SQLite revision 검사는 별도의 최종 무결성 방어선으로 유지됩니다.
    여러 서버 프로세스에서 작동하려면 공유 락이 추가로 필요합니다.
    """

    @wraps(func)
    def guarded(*args, **kwargs):
        session_id = kwargs.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return func(*args, **kwargs)

        with _registry_lock:
            lock = _session_locks.get(session_id)
            if lock is None:
                lock = Lock()
                _session_locks[session_id] = lock

        if not lock.acquire(blocking=False):
            raise ValueError("동일 세션의 이전 대화 요청이 처리 중입니다.")
        try:
            return func(*args, **kwargs)
        finally:
            lock.release()

    return guarded
