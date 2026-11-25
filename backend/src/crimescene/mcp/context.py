
"""Issue #134 - MCP Tool의 서버 검증 실행 컨텍스트.

Python 3.13 / Pydantic 2
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from crimescene.agents.contracts import AgentContext
from crimescene.scenario.evidence_collection import VALID_STAGES
from crimescene.scenario.game_progress import CASE_ID
from crimescene.scenario.schemas.game_state import GameState


@dataclass(frozen=True, slots=True)
class BoundMCPContext:
    """인증된 게임 세션에 바인딩된 내부 실행 컨텍스트.

    MCP Tool의 입력 스키마에 이 객체를 노출하지 않습니다.
    """

    _snapshot: AgentContext = field(repr=False)
    _load_state: Callable[[str], GameState] = field(repr=False)

    @classmethod
    def from_owned_game_state(
        cls,
        *,
        state: GameState,
        load_state: Callable[[str], GameState],
        active_character_id: str | None = None,
    ) -> "BoundMCPContext":
        """FastAPI 소유권 검증이 완료된 이후에만 호출합니다."""

        if not isinstance(state, GameState):
            raise TypeError("GameState가 필요합니다.")

        if state.case_id != CASE_ID:
            raise PermissionError("지원하지 않는 사건입니다.")

        if not callable(load_state):
            raise TypeError("GameState 조회 함수가 필요합니다.")

        if any(
            evidence.stage not in VALID_STAGES
            for evidence in state.evidence.values()
        ):
            raise PermissionError("증거 수집 상태가 올바르지 않습니다.")

        snapshot = AgentContext.from_game_state(
            state,
            active_character_id=active_character_id,
        )

        return cls(
            _snapshot=snapshot,
            _load_state=load_state,
        )

    def load_verified_state(self) -> GameState:
        """Tool 호출 시 서버의 최신 상태를 다시 검증합니다."""

        state = self._load_state(self._snapshot.session_id)

        if not isinstance(state, GameState):
            raise TypeError("올바른 GameState가 필요합니다.")

        if (
            state.case_id != CASE_ID
            or state.session_id != self._snapshot.session_id
        ):
            raise PermissionError("게임 세션 또는 사건이 일치하지 않습니다.")

        if any(
            evidence.stage not in VALID_STAGES
            for evidence in state.evidence.values()
        ):
            raise PermissionError("증거 수집 상태가 올바르지 않습니다.")

        try:
            current = AgentContext.from_game_state(
                state,
                active_character_id=self._snapshot.active_character_id,
            )
        except ValueError:
            raise PermissionError(
                "현재 NPC 접근 권한이 유효하지 않습니다."
            ) from None

        if current != self._snapshot:
            raise RuntimeError(
                "게임 상태가 변경되었습니다. 새로운 실행 컨텍스트가 필요합니다."
            )

        # Tool이 반환 객체를 실수로 수정해도 원본 상태를 보호합니다.
        return state.model_copy(deep=True)

    @property
    def content_version(self) -> str:
        return self._snapshot.content_version

    @property
    def active_character_id(self) -> str | None:
        """서버가 검증한 현재 NPC 식별자입니다."""
        return self._snapshot.active_character_id
