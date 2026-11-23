
"""Issue #133 - Hint Agent 기능 및 보안 테스트."""

import pytest

from crimescene.agents.contracts import AgentContext, AgentRequest, AgentType
from crimescene.agents.hint_agent import HintAgent, HintStatus, parse_hint_level
from crimescene.agents.orchestrator import AgentOrchestrator
from crimescene.agents.registry import AgentRegistry
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GamePhase


def make_rules():
    return {
        "E01": EvidenceRule(
            name="공개 증거 1",
            score=2,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
        "E02": EvidenceRule(
            name="공개 증거 2",
            score=3,
            holder="C02",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
        "E03": EvidenceRule(
            name="미획득 비밀 증거",
            score=1,
            holder="C03",
            prerequisites=[],
            presentation=[],
            q=[],
        ),
    }


def make_state(*, collected=(), unlocked=("C01",)):
    state = transition_phase(
        create_initial_state("HINT-133"),
        GamePhase.INVESTIGATION,
    )
    rules = make_rules()

    state.evidence = {
        item: EvidenceState(stage="found")
        for item in collected
    }
    state.score = sum(rules[item].score for item in collected)
    state.unlocked_characters = list(unlocked)

    return state


def make_agent(state):
    return HintAgent(
        load_state=lambda session_id: state,
        evidence_rules=make_rules(),
    )


def execute(agent, state, message):
    return agent.execute(
        AgentRequest(
            agent_type=AgentType.HINT,
            message=message,
        ),
        context=AgentContext.from_game_state(state),
    )


def test_default_level_one():
    state = make_state()

    result = execute(make_agent(state), state, "힌트 주세요")

    assert result.level == 1
    assert result.chapter == "CH00"
    assert result.source_ids == ()
    assert result.agent_type == AgentType.HINT


def test_explicit_levels():
    assert parse_hint_level("1단계 힌트") == 1
    assert parse_hint_level("2단계 힌트") == 2
    assert parse_hint_level("3단계 힌트") == 3


def test_invalid_level_rejected():
    with pytest.raises(ValueError, match="1~3단계"):
        parse_hint_level("4단계 힌트")


def test_multiple_levels_rejected():
    with pytest.raises(ValueError, match="하나만"):
        parse_hint_level("1단계와 3단계 힌트")


def test_level_two_without_evidence():
    state = make_state()

    result = execute(make_agent(state), state, "2단계 힌트")

    assert result.status == HintStatus.NO_EVIDENCE
    assert result.source_ids == ()
    assert result.collected_count == 0


def test_level_two_with_one_evidence():
    state = make_state(collected=("E01",))

    result = execute(make_agent(state), state, "2단계 힌트")

    assert result.source_ids == ("E01",)
    assert result.collected_count == 1
    assert "E01" in result.text


def test_level_two_with_two_evidence():
    state = make_state(collected=("E01", "E02"))

    result = execute(make_agent(state), state, "2단계 힌트")

    assert result.source_ids == ("E01", "E02")
    assert "E01" in result.text
    assert "E02" in result.text


def test_uncollected_evidence_never_disclosed():
    state = make_state(collected=("E01",))

    result = execute(make_agent(state), state, "2단계 힌트")

    assert "E03" not in result.text
    assert "미획득 비밀 증거" not in result.text
    assert "E03" not in result.source_ids


def test_level_three_uses_unlocked_holder():
    state = make_state(
        collected=("E02",),
        unlocked=("C01", "C02"),
    )

    result = execute(make_agent(state), state, "3단계 힌트")

    assert result.suggested_character_id == "C02"
    assert result.source_ids == ("E02",)
    assert "C02" in result.text


def test_level_three_does_not_reveal_locked_holder():
    state = make_state(
        collected=("E02",),
        unlocked=("C01",),
    )

    result = execute(make_agent(state), state, "3단계 힌트")

    assert result.suggested_character_id == "C01"
    assert "C02" not in result.text


def test_level_three_without_evidence():
    state = make_state()

    result = execute(make_agent(state), state, "3단계 힌트")

    assert result.source_ids == ()
    assert result.status == HintStatus.NO_EVIDENCE
    assert result.suggested_character_id == "C01"


def test_wrong_agent_type_rejected():
    state = make_state()

    with pytest.raises(ValueError, match="Hint Agent"):
        make_agent(state).execute(
            AgentRequest(
                agent_type=AgentType.DEDUCTION,
                message="힌트",
            ),
            context=AgentContext.from_game_state(state),
        )


def test_invalid_phase_rejected():
    state = create_initial_state("HINT-133")

    with pytest.raises(PermissionError, match="조사 단계"):
        execute(make_agent(state), state, "1단계 힌트")


def test_stale_context_rejected():
    state = make_state()
    context = AgentContext.from_game_state(state)

    state.revision += 1

    with pytest.raises(RuntimeError, match="스냅샷"):
        make_agent(state).execute(
            AgentRequest(
                agent_type=AgentType.HINT,
                message="힌트",
            ),
            context=context,
        )


def test_score_inconsistency_rejected():
    state = make_state(collected=("E01",))
    state.score = 0

    with pytest.raises(ValueError, match="점수"):
        execute(make_agent(state), state, "힌트")


def test_orchestrator_read_only():
    state = make_state(collected=("E01",))
    before = state.model_dump(mode="json")

    agent = make_agent(state)
    orchestrator = AgentOrchestrator(
        AgentRegistry([agent]),
        load_state=lambda session_id: state,
    )

    result = orchestrator.execute(
        AgentRequest(
            agent_type=AgentType.HINT,
            message="3단계 힌트",
        ),
        context=AgentContext.from_game_state(state),
    )

    assert result.source_ids == ("E01",)
    assert result.suggested_character_id == "C01"
    assert state.model_dump(mode="json") == before
