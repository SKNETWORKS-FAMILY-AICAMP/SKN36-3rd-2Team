import pytest

from crimescene.scenario.flag_progress import (
    grant_case001_flags,
    parse_flag_source,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)


def make_state(
    *,
    evidence=(),
    npc="C01",
    presented=(),
    flags=(),
):
    state = create_initial_state("test-flags")

    return state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "unlocked_characters": [
                "C01",
                "C03",
                "C04",
                "C06",
                "C08",
                "C10",
            ],
            "evidence": {
                evidence_id: EvidenceState(stage="found") for evidence_id in evidence
            },
            "presented": {npc: list(presented)},
            "flags": list(flags),
        }
    )


def grant(
    flag_id,
    requires,
    source,
    *,
    state,
    npc,
    topics=(),
    presented=None,
):
    return grant_case001_flags(
        state=state,
        active_character_id=npc,
        matched_topics=topics,
        presented_evidence_id=presented,
        flag_requirements={flag_id: frozenset(requires)},
        flag_sources={flag_id: source},
    )


def test_l01_requires_evidence_and_question():
    state = make_state(evidence=("E03",), npc="C06")

    result = grant(
        "L01",
        {"E03"},
        "C06 Q:old_records",
        state=state,
        npc="C06",
        topics=("old_records",),
    )

    assert "L01" in result.flags


def test_l02_c08_presentation():
    state = make_state(
        evidence=("E03", "E04"),
        npc="C08",
        presented=("E04",),
    )

    result = grant(
        "L02",
        {"E03", "E04"},
        "C08 P:E04 or C04 P:E04 & Q:visitor",
        state=state,
        npc="C08",
        presented="E04",
    )

    assert "L02" in result.flags


def test_l02_c04_requires_presentation_and_topic():
    state = make_state(
        evidence=("E03", "E04"),
        npc="C04",
        presented=("E04",),
    )

    kwargs = {
        "flag_id": "L02",
        "requires": {"E03", "E04"},
        "source": "C08 P:E04 or C04 P:E04 & Q:visitor",
        "state": state,
        "npc": "C04",
        "presented": "E04",
    }

    blocked = grant(**kwargs)
    allowed = grant(**kwargs, topics=("visitor",))

    assert "L02" not in blocked.flags
    assert "L02" in allowed.flags


@pytest.mark.parametrize(
    ("npc", "topic"),
    [
        ("C01", "meeting"),
        ("C10", "1405"),
    ],
)
def test_l04_question_routes(npc, topic):
    state = make_state(evidence=("E01",), npc=npc)

    result = grant(
        "L04",
        {"E01"},
        "C01 E01 Q:meeting or C10 Q:1405",
        state=state,
        npc=npc,
        topics=(topic,),
    )

    assert "L04" in result.flags


def test_l03_presentation():
    state = make_state(
        evidence=("E05",),
        npc="C03",
        presented=("E05",),
    )

    result = grant(
        "L03",
        {"E05"},
        "C03 P:E05",
        state=state,
        npc="C03",
        presented="E05",
    )

    assert "L03" in result.flags


def test_l05_presentation():
    state = make_state(
        evidence=("E07",),
        npc="C08",
        presented=("E07",),
    )

    result = grant(
        "L05",
        {"E07"},
        "C08 P:E07",
        state=state,
        npc="C08",
        presented="E07",
    )

    assert "L05" in result.flags


def test_missing_evidence_blocks_flag():
    state = make_state(npc="C06")

    result = grant(
        "L01",
        {"E03"},
        "C06 Q:old_records",
        state=state,
        npc="C06",
        topics=("old_records",),
    )

    assert result.flags == []


def test_unrecorded_presentation_blocks_flag():
    state = make_state(evidence=("E05",), npc="C03")

    result = grant(
        "L03",
        {"E05"},
        "C03 P:E05",
        state=state,
        npc="C03",
        presented="E05",
    )

    assert result.flags == []


def test_duplicate_flag_is_idempotent():
    state = make_state(
        evidence=("E03",),
        npc="C06",
        flags=("L01",),
    )

    result = grant(
        "L01",
        {"E03"},
        "C06 Q:old_records",
        state=state,
        npc="C06",
        topics=("old_records",),
    )

    assert result is state


def test_invalid_source_is_rejected():
    with pytest.raises(ValueError):
        parse_flag_source("C06 UNKNOWN:E03")
