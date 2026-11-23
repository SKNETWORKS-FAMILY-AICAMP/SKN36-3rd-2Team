
"""Issue #130 - Multi-Agent 실행 흐름 및 상태 검증."""

from collections.abc import Callable

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.agents.registry import AgentRegistry
from crimescene.scenario.evidence_collection import VALID_STAGES
from crimescene.scenario.game_progress import CASE_ID
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

READ_ONLY_AGENTS = frozenset({
    AgentType.DEDUCTION,
    AgentType.HINT,
})
class AgentExecutionTimeout(TimeoutError):
    """Agent 내부 실행 제한 시간을 초과했습니다."""

class AgentOrchestrator:
    """서버가 승인한 Agent의 실행을 조정합니다."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        load_state: Callable[[str], GameState],
        load_selection: Callable[
            [str], tuple[str, int] | None
        ] | None = None,
    ) -> None:
        if not isinstance(registry, AgentRegistry):
            raise TypeError("AgentRegistry가 필요합니다.")

        if not callable(load_state):
            raise TypeError("GameState 조회 함수가 필요합니다.")

        if load_selection is not None and not callable(load_selection):
            raise TypeError("NPC 선택 조회 함수가 올바르지 않습니다.")

        self._registry = registry
        self._load_state = load_state
        self._load_selection = load_selection

    def _get_state(self, session_id: str) -> GameState:
        """서버 저장소에서 최신 GameState를 조회합니다."""
        state = self._load_state(session_id)

        if not isinstance(state, GameState):
            raise TypeError("올바른 GameState가 필요합니다.")

        if state.session_id != session_id:
            raise PermissionError("게임 세션이 일치하지 않습니다.")
        if state.case_id != CASE_ID:
            raise PermissionError("지원하지 않는 사건입니다.")
        return state

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> AgentResult:
        """Agent 실행 전후의 게임 상태와 결과를 검증합니다."""

        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest가 필요합니다.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext가 필요합니다.")

        # 1. 서버 저장소에서 최신 상태 재조회
        state = self._get_state(context.session_id)

        expected_context = AgentContext.from_game_state(
            state,
            active_character_id=context.active_character_id,
        )

        if context != expected_context:
            raise RuntimeError(
                "게임 상태 스냅샷이 최신 상태와 다릅니다."
            )

        # 2. 게임 진행 단계 검증
        if (
            state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise PermissionError(
                "현재 게임 단계에서 Agent를 실행할 수 없습니다."
            )

        # 3. NPC 선택 상태 및 revision 검증
        if request.agent_type == AgentType.NPC:
            if context.active_character_id is None:
                raise PermissionError("선택된 NPC가 없습니다.")

            if self._load_selection is None:
                raise RuntimeError("NPC 선택 검증 함수가 없습니다.")

            selection = self._load_selection(context.session_id)

            if selection != (context.active_character_id, state.revision):
                raise PermissionError(
                    "현재 선택된 NPC 또는 revision이 일치하지 않습니다."
                )

        # 4. 증거 수집 상태 검증
        if any(
            evidence.stage not in VALID_STAGES
            for evidence in state.evidence.values()
        ):
            raise PermissionError("유효하지 않은 증거 수집 상태입니다.")

        evidence_id = request.presented_evidence_id

        if evidence_id is not None and evidence_id not in state.evidence:
            raise PermissionError("수집하지 않은 증거입니다.")

        # 5. 등록된 Agent만 실행
        agent = self._registry.resolve(request.agent_type)

        if agent.agent_type != request.agent_type:
            raise RuntimeError("Agent 유형이 일치하지 않습니다.")

        # 읽기 전용 Agent의 상태 변경 탐지를 위한 원본 보관
        original_state = state.model_dump(mode="json")

        # 6. Agent 실행
        try:
            try:
                result = agent.execute(request, context=context)
            except TimeoutError as exc:
                raise AgentExecutionTimeout(
                    "Agent 실행 시간이 초과됐습니다."
                ) from exc
        finally:
            if request.agent_type in READ_ONLY_AGENTS:
                current_state = self._get_state(context.session_id)

                if current_state.model_dump(mode="json") != original_state:
                    raise RuntimeError(
                        "읽기 전용 Agent 실행 중 게임 상태가 변경됐습니다."
                    )

        # 7. 실행 결과 검증
        if not isinstance(result, AgentResult):
            raise TypeError("올바른 AgentResult가 필요합니다.")

        if result.agent_type != request.agent_type:
            raise ValueError("Agent 응답 유형이 일치하지 않습니다.")

        # 8. Deduction / Hint 근거의 획득 여부 검증
        if request.agent_type in READ_ONLY_AGENTS:
            allowed_ids = set(context.collected_evidence_ids)

            if not set(result.source_ids).issubset(allowed_ids):
                raise PermissionError(
                    "미획득 증거를 근거로 사용할 수 없습니다."
                )

        return result
