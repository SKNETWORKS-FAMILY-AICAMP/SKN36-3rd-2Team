"""Issue #23 - NPC별 대화 세션 및 영구 저장소 연동.

기능:
- NPC 선택 및 전환
- 미해금 NPC 접근 차단
- NPC별 대화 기록 분리
- 게임 세션별 기록 분리
- 검증된 NPC 응답만 기록
- GameState revision 검증
- 메모리 및 SQLite 저장 방식 지원

주의:
- 영구 저장소를 지정하지 않으면 기존 메모리 모드로 동작한다.
- 대화 기록은 사건의 검증된 근거가 아니다.
- session_id와 GameState는 신뢰할 수 있는 서버에서 공급해야 한다.
"""

from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.schemas.game_state import GameState

CASE_ID = "CASE-001"

MAX_MESSAGE_LENGTH = 4000
MAX_REPLY_LENGTH = 12000


@dataclass(frozen=True, slots=True)
class NPCExchange:
    """한 번의 플레이어 질문과 검증된 NPC 응답."""

    user_message: str
    npc_message: str
    source_ids: tuple[str, ...]
    state_revision: int


class NPCSessionRepository(Protocol):
    """대화 기록 영구 저장소 인터페이스.

    실제 구현체는 SQLiteNPCSessionRepository를 사용한다.
    """

    def save_selection(
        self,
        session_id: str,
        character_id: str,
        revision: int,
    ) -> None: ...

    def load_selection(
        self,
        session_id: str,
    ) -> tuple[str, int] | None: ...

    def append_exchange(
        self,
        session_id: str,
        character_id: str,
        exchange: NPCExchange,
    ) -> None: ...

    def load_history(
        self,
        session_id: str,
        character_id: str,
    ) -> tuple[NPCExchange, ...]: ...

    def delete_session(
        self,
        session_id: str,
    ) -> None: ...


@dataclass(slots=True)
class _SessionData:
    """메모리 모드의 게임 세션 데이터."""

    active_character_id: str | None = None
    histories: dict[str, deque[NPCExchange]] = field(default_factory=dict)
    latest_revision: int = 0


class NPCSessionStore:
    """NPC 선택 상태와 대화 이력을 관리한다.

    repository=None:
        기존 메모리 기반 관리

    repository=SQLiteNPCSessionRepository(...):
        SQLite 기반 영구 저장
    """

    def __init__(
        self,
        *,
        max_sessions: int = 1000,
        max_exchanges_per_npc: int = 50,
        repository: NPCSessionRepository | None = None,
    ) -> None:
        if isinstance(max_sessions, bool) or not isinstance(max_sessions, int):
            raise TypeError("max_sessions는 정수여야 합니다.")

        if isinstance(max_exchanges_per_npc, bool) or not isinstance(
            max_exchanges_per_npc, int
        ):
            raise TypeError("max_exchanges_per_npc는 정수여야 합니다.")

        if max_sessions < 1 or max_exchanges_per_npc < 1:
            raise ValueError("세션 및 대화 기록 제한은 1 이상이어야 합니다.")

        self._max_sessions = max_sessions
        self._max_exchanges_per_npc = max_exchanges_per_npc

        # 영구 저장소가 지정되면 SQLite를 신뢰 저장소로 사용한다.
        self._repository = repository

        # 기존 메모리 모드 호환성을 유지한다.
        self._sessions: dict[str, _SessionData] = {}

        self._lock = RLock()

    @staticmethod
    def _validate_state(state: GameState) -> None:
        """GameState 기본 검증."""

        if not isinstance(state, GameState):
            raise TypeError("GameState가 필요합니다.")

        if state.case_id != CASE_ID:
            raise ValueError("지원하지 않는 사건 ID입니다.")

        if not state.session_id.strip():
            raise ValueError("게임 세션 ID가 비어 있습니다.")

        if len(state.session_id) > 128:
            raise ValueError("게임 세션 ID가 너무 깁니다.")

    @classmethod
    def _validate_character(
        cls,
        state: GameState,
        character_id: str,
    ) -> None:
        """NPC ID 및 해금 상태 검증."""

        cls._validate_state(state)

        if not isinstance(character_id, str):
            raise TypeError("NPC ID는 문자열이어야 합니다.")

        if character_id not in EXPECTED_CHARACTER_IDS:
            raise ValueError("유효하지 않은 NPC ID입니다.")

        if character_id not in state.unlocked_characters:
            raise PermissionError("아직 해금되지 않은 NPC입니다.")

    @staticmethod
    def _check_revision(
        session: _SessionData,
        state: GameState,
    ) -> None:
        """오래된 게임 상태 사용 방지."""

        if state.revision < session.latest_revision:
            raise ValueError("오래된 GameState revision입니다.")

    @staticmethod
    def _check_stored_revision(
        state: GameState,
        selection: tuple[str, int] | None,
    ) -> None:
        """영구 저장소의 게임 상태 버전 검증."""

        if selection is None:
            return

        _, stored_revision = selection

        if state.revision < stored_revision:
            raise ValueError("오래된 GameState revision입니다.")

    def _get_or_create_session(
        self,
        state: GameState,
    ) -> _SessionData:
        """메모리 모드에서 세션을 조회하거나 생성한다."""

        session = self._sessions.get(state.session_id)

        if session is None:
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError("허용된 게임 세션 수를 초과했습니다.")

            session = _SessionData(
                latest_revision=state.revision,
            )

            self._sessions[state.session_id] = session

        self._check_revision(session, state)

        return session

    def select_npc(
        self,
        state: GameState,
        character_id: str,
    ) -> tuple[NPCExchange, ...]:
        """NPC를 선택하고 해당 NPC의 대화 기록을 반환한다."""

        self._validate_character(state, character_id)

        with self._lock:
            # SQLite 영구 저장 모드
            if self._repository is not None:
                self._repository.save_selection(
                    state.session_id,
                    character_id,
                    state.revision,
                )

                return self._repository.load_history(
                    state.session_id,
                    character_id,
                )

            # 기존 메모리 모드
            session = self._get_or_create_session(state)

            session.active_character_id = character_id
            session.latest_revision = state.revision

            history = session.histories.get(character_id)

            return tuple(history) if history is not None else ()

    def get_active_npc(
        self,
        state: GameState,
    ) -> str | None:
        """현재 선택된 NPC를 반환한다."""

        self._validate_state(state)

        with self._lock:
            # SQLite 모드
            if self._repository is not None:
                selection = self._repository.load_selection(state.session_id)

                if selection is None:
                    return None

                self._check_stored_revision(state, selection)

                active_id, _ = selection

                if active_id not in state.unlocked_characters:
                    return None

                return active_id

            # 메모리 모드
            session = self._sessions.get(state.session_id)

            if session is None:
                return None

            self._check_revision(session, state)

            active_id = session.active_character_id

            if active_id not in state.unlocked_characters:
                return None

            return active_id

    def get_history(
        self,
        state: GameState,
        character_id: str,
    ) -> tuple[NPCExchange, ...]:
        """지정한 NPC의 대화 기록만 반환한다."""

        self._validate_character(state, character_id)

        with self._lock:
            # SQLite 모드
            if self._repository is not None:
                selection = self._repository.load_selection(state.session_id)

                if selection is None:
                    return ()

                self._check_stored_revision(state, selection)

                return self._repository.load_history(
                    state.session_id,
                    character_id,
                )

            # 메모리 모드
            session = self._sessions.get(state.session_id)

            if session is None:
                return ()

            self._check_revision(session, state)

            history = session.histories.get(character_id)

            return tuple(history) if history is not None else ()

    def append_verified_exchange(
        self,
        state: GameState,
        character_id: str,
        *,
        user_message: str,
        reply: NPCGroundedReply,
    ) -> NPCExchange:
        """검증된 NPC 응답을 대화 기록에 추가한다.

        기존 보안 검증 결과 형태를 검사한다.
        원시 LLM 문자열이나 임의의 자유 생성 답변은 거부한다.
        """

        self._validate_character(state, character_id)

        # 플레이어 메시지 검증
        if not isinstance(user_message, str):
            raise TypeError("플레이어 메시지는 문자열이어야 합니다.")

        question = user_message.strip()

        if not question:
            raise ValueError("플레이어 메시지가 비어 있습니다.")

        if len(question) > MAX_MESSAGE_LENGTH:
            raise ValueError("플레이어 메시지가 너무 깁니다.")

        # NPC 응답 타입 검증
        if not isinstance(reply, NPCGroundedReply):
            raise TypeError("NPCGroundedReply가 필요합니다.")

        if not isinstance(reply.text, str):
            raise TypeError("NPC 응답은 문자열이어야 합니다.")

        if not isinstance(reply.grounded, bool):
            raise TypeError("grounded는 bool이어야 합니다.")

        answer = reply.text.strip()

        if not answer:
            raise ValueError("NPC 응답이 비어 있습니다.")

        if len(answer) > MAX_REPLY_LENGTH:
            raise ValueError("NPC 응답이 너무 깁니다.")

        source_ids = reply.source_ids

        if not isinstance(source_ids, tuple):
            raise TypeError("출처 ID 목록은 튜플이어야 합니다.")

        if any(
            not isinstance(source_id, str) or not source_id.strip()
            for source_id in source_ids
        ):
            raise ValueError("잘못된 출처 ID입니다.")

        if len(source_ids) != len(set(source_ids)):
            raise ValueError("중복된 출처 ID입니다.")

        # 승인된 근거가 있는 응답만 저장한다.
        if reply.grounded:
            if not source_ids:
                raise ValueError("근거 검증 응답에는 출처가 필요합니다.")

        elif answer != FALLBACK_REPLY or source_ids:
            raise ValueError("검증되지 않은 NPC 응답은 저장할 수 없습니다.")

        exchange = NPCExchange(
            user_message=question,
            npc_message=answer,
            source_ids=source_ids,
            state_revision=state.revision,
        )

        with self._lock:
            # SQLite 모드
            if self._repository is not None:
                selection = self._repository.load_selection(state.session_id)

                if selection is None:
                    raise PermissionError("선택된 NPC가 없습니다.")

                self._check_stored_revision(state, selection)

                active_id, _ = selection

                if active_id != character_id:
                    raise PermissionError("현재 선택된 NPC가 아닙니다.")

                self._repository.append_exchange(
                    state.session_id,
                    character_id,
                    exchange,
                )

                return exchange

            # 메모리 모드
            session = self._get_or_create_session(state)

            if session.active_character_id != character_id:
                raise PermissionError("현재 선택된 NPC가 아닙니다.")

            history = session.histories.setdefault(
                character_id,
                deque(maxlen=self._max_exchanges_per_npc),
            )

            history.append(exchange)
            session.latest_revision = state.revision

        return exchange

    def clear_session(self, state: GameState) -> None:
        """현재 게임 세션의 모든 대화 기록을 삭제한다."""

        self._validate_state(state)

        with self._lock:
            # SQLite 모드
            if self._repository is not None:
                selection = self._repository.load_selection(state.session_id)

                self._check_stored_revision(state, selection)

                self._repository.delete_session(state.session_id)

                return

            # 메모리 모드
            session = self._sessions.get(state.session_id)

            if session is not None:
                self._check_revision(session, state)

                del self._sessions[state.session_id]
