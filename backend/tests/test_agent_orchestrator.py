
"""Issue #130 - Agent Orchestrator 테스트."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.agents.orchestrator import AgentExecutionTimeout, AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import GamePhase


class StubAgent:
    """외부 서비스에 연결하지 않는 테스트용 Agent."""

    def __init__(self, agent_type: AgentType) -> None:
        self._agent_type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> AgentResult:
        return AgentResult(
            agent_type=self.agent_type,
            text="테스트 응답",
        )


def test_registry_resolves_agent():
    agent = StubAgent(AgentType.NPC)
    registry = AgentRegistry([agent])

    assert registry.resolve(AgentType.NPC) is agent


def test_registry_rejects_duplicate_agent():
    agents = [
        StubAgent(AgentType.NPC),
        StubAgent(AgentType.NPC),
    ]

    with pytest.raises(ValueError, match="중복"):
        AgentRegistry(agents)


def test_registry_rejects_invalid_executor():
    with pytest.raises(TypeError):
        AgentRegistry([object()])


def test_registry_rejects_missing_execute():
    class InvalidAgent:
        agent_type = AgentType.HINT

    with pytest.raises(TypeError):
        AgentRegistry([InvalidAgent()])


def test_registry_rejects_unregistered_agent():
    registry = AgentRegistry()

    with pytest.raises(LookupError, match="등록되지 않은"):
        registry.resolve(AgentType.HINT)


def test_registry_rejects_invalid_agent_type():
    registry = AgentRegistry()

    with pytest.raises(TypeError):
        registry.resolve("unknown")


def make_orchestrator(
    agent: StubAgent,
    *,
    investigation: bool = True,
):
    """서버 상태 저장소를 모방하는 테스트 환경."""
    state = create_initial_state("session-130")

    if investigation:
        state = transition_phase(
            state,
            GamePhase.INVESTIGATION,
        )

    states = {state.session_id: state}

    orchestrator = AgentOrchestrator(
        AgentRegistry([agent]),
        load_state=lambda session_id: states[session_id],
        load_selection=lambda session_id: (
            "C01",
            states[session_id].revision,
        ),
    )

    context = AgentContext.from_game_state(
        state,
        active_character_id="C01",
    )

    return orchestrator, context, states


def test_orchestrator_routes_agent():
    orchestrator, context, _ = make_orchestrator(
        StubAgent(AgentType.HINT)
    )

    result = orchestrator.execute(
        AgentRequest(
            agent_type=AgentType.HINT,
            message="힌트를 알려주세요",
        ),
        context=context,
    )

    assert result.agent_type == AgentType.HINT
    assert result.text == "테스트 응답"


def test_orchestrator_rejects_stale_revision():
    orchestrator, context, states = make_orchestrator(
        StubAgent(AgentType.HINT)
    )

    states[context.session_id].revision += 1

    with pytest.raises(RuntimeError, match="최신 상태"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=context,
        )


def test_orchestrator_rejects_invalid_phase():
    orchestrator, context, _ = make_orchestrator(
        StubAgent(AgentType.HINT),
        investigation=False,
    )

    with pytest.raises(PermissionError, match="게임 단계"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=context,
        )


def test_orchestrator_requires_selected_npc():
    orchestrator, context, states = make_orchestrator(
        StubAgent(AgentType.NPC)
    )

    context = AgentContext.from_game_state(
        states[context.session_id],
    )

    with pytest.raises(PermissionError, match="선택된 NPC"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.NPC,
                message="안녕하세요",
            ),
            context=context,
        )


def test_orchestrator_rejects_uncollected_evidence():
    orchestrator, context, _ = make_orchestrator(
        StubAgent(AgentType.NPC)
    )

    with pytest.raises(PermissionError, match="수집하지 않은"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.NPC,
                message="이 증거를 보세요",
                presented_evidence_id="E01",
            ),
            context=context,
        )


def test_orchestrator_detects_read_only_mutation():
    states = {}

    class MutatingAgent(StubAgent):
        def execute(self, request, *, context):
            states[context.session_id].revision += 1
            return super().execute(request, context=context)

    state = transition_phase(
        create_initial_state("session-mutation"),
        GamePhase.INVESTIGATION,
    )
    states[state.session_id] = state

    orchestrator = AgentOrchestrator(
        AgentRegistry([MutatingAgent(AgentType.HINT)]),
        load_state=lambda session_id: states[session_id],
    )

    with pytest.raises(RuntimeError, match="상태가 변경"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=AgentContext.from_game_state(state),
        )


def test_orchestrator_rejects_unowned_source():
    class LeakyAgent(StubAgent):
        def execute(self, request, *, context):
            return AgentResult(
                agent_type=self.agent_type,
                text="테스트 응답",
                source_ids=("E01",),
            )

    orchestrator, context, _ = make_orchestrator(
        LeakyAgent(AgentType.DEDUCTION)
    )

    with pytest.raises(PermissionError, match="미획득 증거"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message="추리를 검토해 주세요",
            ),
            context=context,
        )


def test_orchestrator_rejects_invalid_result():
    """AgentResult가 아닌 결과는 거부합니다."""

    class InvalidResultAgent(StubAgent):
        def execute(self, request, *, context):
            return {"text": "잘못된 응답"}

    orchestrator, context, _ = make_orchestrator(
        InvalidResultAgent(AgentType.HINT)
    )

    with pytest.raises(TypeError, match="AgentResult"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트를 알려주세요",
            ),
            context=context,
        )


def test_orchestrator_rejects_mismatched_result_type():
    """요청과 다른 Agent 유형의 결과를 거부합니다."""

    class MismatchedAgent(StubAgent):
        def execute(self, request, *, context):
            return AgentResult(
                agent_type=AgentType.NPC,
                text="잘못된 Agent 응답",
            )

    orchestrator, context, _ = make_orchestrator(
        MismatchedAgent(AgentType.HINT)
    )

    with pytest.raises(ValueError, match="응답 유형"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트를 알려주세요",
            ),
            context=context,
        )


def test_orchestrator_propagates_agent_error():
    """Agent 실행 실패 시 정상 응답으로 처리하지 않습니다."""

    class FailingAgent(StubAgent):
        def execute(self, request, *, context):
            raise RuntimeError("Agent execution failed")

    orchestrator, context, _ = make_orchestrator(
        FailingAgent(AgentType.HINT)
    )

    with pytest.raises(RuntimeError, match="execution failed"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트를 알려주세요",
            ),
            context=context,
        )


def test_orchestrator_detects_mutation_on_error():
    """Agent 예외 발생 시에도 읽기 전용 상태 변경을 탐지합니다."""

    states = {}

    class MutatingFailAgent(StubAgent):
        def execute(self, request, *, context):
            states[context.session_id].revision += 1
            raise ValueError("Agent failed")

    state = transition_phase(
        create_initial_state("session-error-130"),
        GamePhase.INVESTIGATION,
    )
    states[state.session_id] = state

    orchestrator = AgentOrchestrator(
        AgentRegistry([MutatingFailAgent(AgentType.HINT)]),
        load_state=lambda session_id: states[session_id],
    )

    with pytest.raises(RuntimeError, match="상태가 변경"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=AgentContext.from_game_state(state),
        )


def test_orchestrator_rejects_cross_session_state():
    """요청 세션과 저장소가 반환한 세션이 다르면 차단합니다."""

    state_a = transition_phase(
        create_initial_state("session-a"),
        GamePhase.INVESTIGATION,
    )

    state_b = transition_phase(
        create_initial_state("session-b"),
        GamePhase.INVESTIGATION,
    )

    orchestrator = AgentOrchestrator(
        AgentRegistry([StubAgent(AgentType.HINT)]),
        load_state=lambda session_id: state_a,
    )

    with pytest.raises(PermissionError, match="세션"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=AgentContext.from_game_state(state_b),
        )


def test_orchestrator_rejects_changed_snapshot():
    """revision이 같더라도 컨텍스트 내용이 다르면 거부합니다."""

    orchestrator, context, states = make_orchestrator(
        StubAgent(AgentType.HINT)
    )

    # revision 증가 없이 서버 상태 변경
    states[context.session_id].unlocked_characters.append("C02")

    with pytest.raises(RuntimeError, match="최신 상태"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트를 알려주세요",
            ),
            context=context,
        )


@pytest.mark.parametrize(
    "selection",
    [None, ("C02", 1), ("C01", 999)],
)
def test_orchestrator_rejects_invalid_selection(selection):
    """실제 선택 NPC와 revision이 다르면 차단합니다."""
    state = transition_phase(
        create_initial_state("session-selection-130"),
        GamePhase.INVESTIGATION,
    )

    orchestrator = AgentOrchestrator(
        AgentRegistry([StubAgent(AgentType.NPC)]),
        load_state=lambda _: state,
        load_selection=lambda _: selection,
    )

    context = AgentContext.from_game_state(
        state,
        active_character_id="C01",
    )

    with pytest.raises(PermissionError, match="현재 선택된 NPC"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.NPC,
                message="안녕하세요",
            ),
            context=context,
        )


def test_orchestrator_rejects_invalid_evidence_stage():
    """비정상 증거 상태를 보유 증거로 인정하지 않습니다."""
    from crimescene.scenario.schemas.game_state import EvidenceState

    state = transition_phase(
        create_initial_state("session-stage-130"),
        GamePhase.INVESTIGATION,
    )
    state.evidence["E01"] = EvidenceState(stage="locked")

    orchestrator = AgentOrchestrator(
        AgentRegistry([StubAgent(AgentType.HINT)]),
        load_state=lambda _: state,
    )

    with pytest.raises(PermissionError, match="증거 수집 상태"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트를 알려주세요",
            ),
            context=AgentContext.from_game_state(state),
        )


def test_orchestrator_normalizes_timeout():
    """Agent 타임아웃을 공통 예외로 변환합니다."""

    class TimeoutAgent(StubAgent):
        def execute(self, request, *, context):
            raise TimeoutError("External service timeout")

    orchestrator, context, _ = make_orchestrator(
        TimeoutAgent(AgentType.HINT)
    )

    with pytest.raises(
        AgentExecutionTimeout,
        match="실행 시간이 초과",
    ):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=context,
        )


def test_orchestrator_rejects_unsupported_case():
    """CASE-001 이외의 사건을 실행하지 않습니다."""

    state = transition_phase(
        create_initial_state("session-invalid-case"),
        GamePhase.INVESTIGATION,
    )
    state.case_id = "CASE-999"

    orchestrator = AgentOrchestrator(
        AgentRegistry([StubAgent(AgentType.HINT)]),
        load_state=lambda _: state,
    )

    with pytest.raises(PermissionError, match="지원하지 않는 사건"):
        orchestrator.execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=AgentContext.from_game_state(state),
        )


def test_orchestrator_isolates_concurrent_sessions():
    """동시 요청에서도 각 세션의 컨텍스트를 유지합니다."""

    barrier = Barrier(2)

    class SessionAwareAgent(StubAgent):
        def execute(self, request, *, context):
            barrier.wait(timeout=5)
            return AgentResult(
                agent_type=self.agent_type,
                text=context.session_id,
            )

    states = {
        session_id: transition_phase(
            create_initial_state(session_id),
            GamePhase.INVESTIGATION,
        )
        for session_id in ("session-a", "session-b")
    }

    orchestrator = AgentOrchestrator(
        AgentRegistry([SessionAwareAgent(AgentType.HINT)]),
        load_state=lambda session_id: states[session_id],
    )

    request = AgentRequest(
        agent_type=AgentType.HINT,
        message="힌트",
    )

    def execute_for(session_id: str) -> str:
        context = AgentContext.from_game_state(states[session_id])

        return orchestrator.execute(
            request,
            context=context,
        ).text

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                execute_for,
                ("session-a", "session-b"),
            )
        )

    assert results == ["session-a", "session-b"]
