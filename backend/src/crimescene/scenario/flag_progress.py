"""Issue #28 - CASE-001 이벤트 기반 플래그 발급."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)

SOURCE_PATTERN = re.compile(
    r"(?P<npc>C(?:0[1-9]|10))"
    r"(?: (?P<extra>E\d{2}))?"
    r"(?: P:(?P<presented>E\d{2})(?: & Q:(?P<joint_topic>[a-z0-9_]+))?"
    r"| Q:(?P<topic>[a-z0-9_]+))"
)


@dataclass(frozen=True, slots=True)
class FlagSource:
    npc_id: str
    required_evidence: str | None
    presented_evidence: str | None
    required_topic: str | None


def parse_flag_source(source: str) -> tuple[FlagSource, ...]:
    """source의 OR 조건을 개별 이벤트 조건으로 변환합니다."""

    if not isinstance(source, str):
        raise TypeError("플래그 source는 문자열이어야 합니다.")

    conditions = []

    for expression in source.split(" or "):
        match = SOURCE_PATTERN.fullmatch(expression)

        if match is None:
            raise ValueError(f"지원하지 않는 플래그 source: {expression}")

        conditions.append(
            FlagSource(
                npc_id=match.group("npc"),
                required_evidence=match.group("extra"),
                presented_evidence=match.group("presented"),
                required_topic=(match.group("joint_topic") or match.group("topic")),
            )
        )

    return tuple(conditions)


def grant_case001_flags(
    *,
    state: GameState,
    active_character_id: str,
    matched_topics: Iterable[str],
    presented_evidence_id: str | None,
    flag_requirements: Mapping[str, frozenset[str]],
    flag_sources: Mapping[str, str],
) -> GameState:
    """검증된 대화·증거 제시 이벤트에 대해서만 플래그를 지급합니다.

    matched_topics는 PolicyEvaluator를 통과한 서버 결과여야 합니다.
    presented_evidence_id는 제시 검증이 완료된 값이어야 합니다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    if isinstance(matched_topics, (str, bytes)):
        raise TypeError("matched_topics는 문자열 목록이어야 합니다.")

    if not isinstance(flag_requirements, Mapping):
        raise TypeError("플래그 선행 조건이 올바르지 않습니다.")

    if not isinstance(flag_sources, Mapping):
        raise TypeError("플래그 이벤트 조건이 올바르지 않습니다.")

    if set(flag_requirements) != set(flag_sources):
        raise ValueError("플래그 조건과 이벤트 조건이 일치하지 않습니다.")

    valid_flags = {f"L{i:02d}" for i in range(1, 6)}

    if not set(flag_requirements).issubset(valid_flags):
        raise ValueError("등록되지 않은 진행 플래그가 있습니다.")

    # 모든 규칙을 먼저 검증합니다.
    parsed_sources = {}

    for flag_id, source in flag_sources.items():
        required = flag_requirements[flag_id]

        if not isinstance(required, frozenset):
            raise TypeError("플래그 선행 조건은 frozenset이어야 합니다.")

        parsed_sources[flag_id] = parse_flag_source(source)

    if (
        state.phase != GamePhase.INVESTIGATION
        or state.outcome not in (None, "ONGOING")
        or active_character_id not in state.unlocked_characters
    ):
        return state

    topics = set(matched_topics)

    if any(not isinstance(topic, str) for topic in topics):
        raise TypeError("대화 주제는 문자열이어야 합니다.")

    collected = {
        evidence_id
        for evidence_id, evidence_state in state.evidence.items()
        if evidence_state.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
    }

    new_flags = []

    for flag_id in sorted(flag_requirements):
        if flag_id in state.flags:
            continue

        required = flag_requirements[flag_id]

        # 먼저 증거 선행 조건을 확인합니다.
        if not required.issubset(collected):
            continue

        for source in parsed_sources[flag_id]:
            if source.npc_id != active_character_id:
                continue

            if (
                source.required_evidence is not None
                and source.required_evidence not in collected
            ):
                continue

            if (
                source.required_topic is not None
                and source.required_topic not in topics
            ):
                continue

            if source.presented_evidence is not None:
                evidence_id = source.presented_evidence

                if (
                    presented_evidence_id != evidence_id
                    or evidence_id not in collected
                    or evidence_id not in state.presented.get(active_character_id, [])
                ):
                    continue

            new_flags.append(flag_id)
            break

    if not new_flags:
        return state

    return GameState.model_validate(
        {
            **state.model_dump(),
            "flags": [*state.flags, *new_flags],
            "revision": state.revision + 1,
        }
    )
