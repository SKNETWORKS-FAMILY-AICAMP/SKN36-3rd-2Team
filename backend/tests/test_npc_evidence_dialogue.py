"""Issue #174 - evidence context and display security."""

from dataclasses import replace

import pytest

from crimescene.chat.npc_evidence_dialogue import (
    NPC_IDS,
    build_evidence_dialogue_context,
    build_evidence_dialogue_prompt,
    get_evidence_dialogue_opener,
    allowed_evidence_dialogue_openers,
)
from crimescene.chat.npc_emotional_state import NPCEmotionalState
from crimescene.chat.npc_history_display import (
    is_valid_stored_display,
)
from crimescene.retriever.authorized_multisource_context import (
    AuthorizedMultisourceContext,
    AuthorizedMultisourceItem,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GameState,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.evidence_presentation import (
    record_evidence_presentation,
)


def make_state(evidence_id="E01"):
    return GameState(
        case_id="CASE-001",
        session_id="EVIDENCE-174",
        content_version="case001_1120",
        unlocked_characters=sorted(NPC_IDS),
        evidence={
            evidence_id: EvidenceState(stage="found"),
        },
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def present(state, npc="C01", evidence_id="E01"):
    return record_evidence_presentation(
        state=state,
        active_character_id=npc,
        evidence_id=evidence_id,
        evidence_rules={
            evidence_id: EvidenceRule(
                name="테스트 자료",
                score=1,
                holder=npc,
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        allowed_recipients={
            evidence_id: frozenset({npc})
        },
    )


def derive(before, result, npc="C01", eid="E01"):
    return build_evidence_dialogue_context(
        before=before,
        after=result.state,
        character_id=npc,
        evidence_id=eid,
        presentation_created=result.created,
    )


def test_first_presentation():
    before = make_state()
    original = before.model_dump()

    result = present(before)
    context = derive(before, result)

    assert context.first_presentation is True
    assert context.revision == 1
    assert context.character_id == "C01"
    assert context.evidence_id == "E01"

    assert before.model_dump() == original
    assert result.state.score == before.score


def test_repeated_presentation():
    before = make_state()
    first = present(before)
    second = present(first.state)

    context = derive(first.state, second)

    assert context.first_presentation is False
    assert second.state.revision == first.state.revision
    assert second.state.presented == {"C01": ["E01"]}
    assert second.state.score == first.state.score


def test_first_presentation_is_npc_specific():
    before = make_state()

    first = present(before, "C01")
    second = present(first.state, "C02")

    context = derive(first.state, second, "C02")

    assert context.first_presentation is True
    assert second.state.presented == {
        "C01": ["E01"],
        "C02": ["E01"],
    }


def test_forged_presentation_status_rejected():
    before = make_state()
    first = present(before)

    with pytest.raises(PermissionError):
        build_evidence_dialogue_context(
            before=before,
            after=first.state,
            character_id="C01",
            evidence_id="E01",
            presentation_created=False,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": "OTHER"},
        {"character_id": "C02"},
        {"revision": 999},
        {"revision": -1},
        {"evidence_id": "E26"},
        {"evidence_id": "E30"},
        {"evidence_id": "E99"},
        {"evidence_id": "E02"},
    ],
)
def test_forged_context_rejected(changes):
    before = make_state()
    first = present(before)
    context = derive(before, first)

    forged = replace(context, **changes)

    with pytest.raises(PermissionError):
        forged.validate(first.state, "C01")


def test_uncollected_context_rejected():
    before = make_state()
    first = present(before)
    context = derive(before, first)

    invalid = first.state.model_copy(
        update={"evidence": {}}
    )

    with pytest.raises(PermissionError):
        context.validate(invalid, "C01")


def test_unpresented_context_rejected():
    before = make_state()
    first = present(before)
    context = derive(before, first)

    invalid = first.state.model_copy(
        update={"presented": {}}
    )

    with pytest.raises(PermissionError):
        context.validate(invalid, "C01")


def test_locked_npc_context_rejected():
    before = make_state()
    first = present(before)
    context = derive(before, first)

    invalid = first.state.model_copy(
        update={"unlocked_characters": ["C02"]}
    )

    with pytest.raises(PermissionError):
        context.validate(invalid, "C01")


@pytest.mark.parametrize("eid", ["E26", "E30"])
def test_protected_evidence_still_blocked(eid):
    before = make_state(eid)
    original = before.model_dump()

    with pytest.raises(PermissionError):
        present(before, evidence_id=eid)

    assert before.model_dump() == original


def test_evidence_prompt_without_direct_source():
    before = make_state()
    first = present(before)
    evidence = derive(before, first)

    context = AuthorizedMultisourceContext(
        items=(),
        text="",
    )

    prompt = build_evidence_dialogue_prompt(
        evidence, context
    )

    assert "최초 제시" in prompt
    assert "직접 증거 항목이 확인되지 않았다" in prompt
    assert "새로운 정보 공개 권한이 아니다" in prompt


def test_evidence_prompt_with_direct_authorized_source():
    before = make_state()
    first = present(before)
    evidence = derive(before, first)

    item = AuthorizedMultisourceItem(
        kind="evidence",
        item_id="E01",
        source_id="E01",
        score=0.1,
        methods=("graph",),
        content="PRIVATE_SOURCE_BODY_SENTINEL",
        truth_status=None,
    )

    context = AuthorizedMultisourceContext(
        items=(item,),
        text=item.content,
    )

    prompt = build_evidence_dialogue_prompt(
        evidence, context
    )

    assert "직접 근거가 있다" in prompt

    # Source body stays in verified_context, not system guidance.
    assert item.content not in prompt
    assert "E01" not in prompt


QUOTE = "당시 자료를 확인한 기록입니다."
SOURCE = "TEST-SOURCE-174"
CANONICAL = (
    "제가 확인한 자료에는 이렇게 나와 있어요.\n"
    f"“{QUOTE}” (근거: {SOURCE})"
)


@pytest.mark.parametrize("npc", sorted(NPC_IDS))
@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize(
    "scores",
    [
        (50, 20, 20),
        (40, 45, 60),
        (20, 85, 90),
    ],
)
def test_evidence_openers_are_restorable(
    npc,
    repeated,
    scores,
):
    before = make_state()
    first = present(before, npc)

    if repeated:
        before = first.state
        result = present(before, npc)
    else:
        result = first

    evidence = derive(before, result, npc)
    emotion = NPCEmotionalState(npc, *scores)

    opener = get_evidence_dialogue_opener(
        evidence, emotion
    )

    if opener is None:
        assert not repeated
        return

    assert opener in allowed_evidence_dialogue_openers(npc)

    display = f"{opener}\n“{QUOTE}”"

    assert is_valid_stored_display(
        CANONICAL,
        (SOURCE,),
        npc,
        display,
    )


def test_evidence_display_rejects_added_fact():
    opener = allowed_evidence_dialogue_openers("C01")[0]

    assert not is_valid_stored_display(
        CANONICAL,
        (SOURCE,),
        "C01",
        f"{opener}\n“{QUOTE}”\n조작된 사건 정보",
    )


def test_other_npc_emotion_rejected():
    before = make_state()
    result = present(before)
    context = derive(before, result)

    with pytest.raises(ValueError):
        get_evidence_dialogue_opener(
            context,
            NPCEmotionalState("C02"),
        )


# Issue #175 - context-aware vector query

from crimescene.chat.npc_context_query import (
    build_evidence_search_query,
)


def make_query_rules():
    return {
        "E01": EvidenceRule(
            name="Emergency exit records",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }


def build_test_query(question, state, context, **kwargs):
    return build_evidence_search_query(
        question,
        state=state,
        character_id=kwargs.get("npc", "C01"),
        evidence_dialogue=context,
        evidence_rules=kwargs.get(
            "rules", make_query_rules()
        ),
    )


def test_context_query_preserves_original():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    original = "Explain this evidence."

    result = build_test_query(
        original, event.state, context
    )

    assert result.startswith(original + " ")
    assert result.endswith(
        "E01 Emergency exit records"
    )


def test_context_query_does_not_duplicate_title():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    original = "Explain Emergency exit records."

    result = build_test_query(
        original, event.state, context
    )

    assert result == original + " E01"


def test_context_query_is_idempotent():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    original = "Explain E01 Emergency exit records."

    assert build_test_query(
        original, event.state, context
    ) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "OTHER-SESSION"),
        ("revision", 999),
        ("evidence_id", "E26"),
        ("evidence_id", "E30"),
        ("character_id", "C02"),
    ],
)
def test_context_query_rejects_invalid_context(
    field,
    value,
):
    before = make_state()
    event = present(before)
    context = derive(before, event)

    invalid = replace(context, **{field: value})

    with pytest.raises(PermissionError):
        build_test_query(
            "Explain this evidence.",
            event.state,
            invalid,
        )


def test_context_query_rejects_unpresented_evidence():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    changed = event.state.model_copy(
        update={"presented": {}}
    )

    with pytest.raises(PermissionError):
        build_test_query(
            "Explain this evidence.",
            changed,
            context,
        )


def test_context_query_rejects_unknown_rule():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    with pytest.raises(PermissionError):
        build_test_query(
            "Explain this evidence.",
            event.state,
            context,
            rules={},
        )


def test_context_query_does_not_mutate_state():
    before = make_state()
    event = present(before)
    context = derive(before, event)

    snapshot = event.state.model_dump()

    build_test_query(
        "Explain this evidence.",
        event.state,
        context,
    )

    assert event.state.model_dump() == snapshot


def test_context_query_preserves_max_length():
    from crimescene.chat.npc_session import (
        MAX_MESSAGE_LENGTH,
    )

    before = make_state()
    event = present(before)
    context = derive(before, event)

    question = "x" * MAX_MESSAGE_LENGTH

    assert build_test_query(
        question, event.state, context
    ) == question
