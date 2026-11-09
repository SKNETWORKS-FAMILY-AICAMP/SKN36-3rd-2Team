"""Issue #28 - 증거 수집 및 점수 관리."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
    GameState,
)

VALID_STAGES = frozenset({"found", "resolved"})


@dataclass(frozen=True, slots=True)
class CollectionProgress:
    score: int
    total: int
    collected_count: int
    total_count: int


@dataclass(frozen=True, slots=True)
class EvidenceCollectionResult:
    state: GameState
    created: bool
    progress: CollectionProgress


def get_collection_progress(
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule],
) -> CollectionProgress:
    """고유 증거 ID를 기준으로 수집 점수를 계산합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(evidence_rules, Mapping) or not evidence_rules:
        raise ValueError("유효한 증거 규칙이 필요합니다.")

    if any(not isinstance(rule, EvidenceRule) for rule in evidence_rules.values()):
        raise TypeError("증거 규칙 타입이 올바르지 않습니다.")

    score = 0
    count = 0

    for evidence_id, evidence_state in state.evidence.items():
        rule = evidence_rules.get(evidence_id)

        if rule is None:
            raise ValueError("등록되지 않은 증거입니다.")

        if not isinstance(rule, EvidenceRule):
            raise TypeError("증거 규칙 타입이 올바르지 않습니다.")

        if evidence_state.stage not in VALID_STAGES:
            raise ValueError("올바르지 않은 증거 진행 상태입니다.")

        score += rule.score
        count += 1

    return CollectionProgress(
        score=score,
        total=sum(rule.score for rule in evidence_rules.values()),
        collected_count=count,
        total_count=len(evidence_rules),
    )


def collect_evidence(
    *,
    state: GameState,
    evidence_id: str,
    evidence_rules: Mapping[str, EvidenceRule],
    acquisition_policy_ids: Mapping[str, str],
    evaluator: PolicyEvaluator,
    active_character_id: str,
) -> EvidenceCollectionResult:
    """서버 접근 정책을 통과한 증거만 수집합니다."""

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    if state.phase != GamePhase.INVESTIGATION:
        raise PermissionError("조사 단계에서만 증거를 수집할 수 있습니다.")

    if state.outcome not in (None, "ONGOING"):
        raise PermissionError("종료된 게임입니다.")

    if active_character_id not in state.unlocked_characters:
        raise PermissionError("해금되지 않은 NPC입니다.")

    if not isinstance(evidence_id, str):
        raise TypeError("증거 ID는 문자열이어야 합니다.")

    rule = evidence_rules.get(evidence_id)

    if rule is None:
        raise ValueError("등록되지 않은 증거입니다.")

    if not isinstance(rule, EvidenceRule):
        raise TypeError("증거 규칙 타입이 올바르지 않습니다.")

    progress = get_collection_progress(state, evidence_rules)

    # 기존 점수와 수집된 증거가 불일치하면 진행을 중단합니다.
    if state.score != progress.score:
        raise ValueError("증거 수집 점수의 무결성이 일치하지 않습니다.")

    # 중복 수집 시 점수 및 revision을 변경하지 않습니다.
    if evidence_id in state.evidence:
        return EvidenceCollectionResult(
            state=state,
            created=False,
            progress=progress,
        )

    # 선행 증거 ID는 검증하고, 해석되지 않은 조건은 거부합니다.
    for prerequisite in rule.prerequisites:
        if not re.fullmatch(r"E\d{2}", prerequisite):
            raise PermissionError("검증되지 않은 증거 선행 조건입니다.")

        previous = state.evidence.get(prerequisite)

        if previous is None or previous.stage not in VALID_STAGES:
            raise PermissionError("선행 증거를 아직 수집하지 않았습니다.")

    # 수집 권한은 서버에 등록된 정책으로만 검증합니다.
    policy_id = acquisition_policy_ids.get(evidence_id)

    if not isinstance(policy_id, str) or not evaluator.is_allowed(
        policy_id,
        state,
        active_character_id=active_character_id,
    ):
        raise PermissionError("증거 수집 조건을 충족하지 않았습니다.")

    next_evidence = {
        **state.evidence,
        evidence_id: EvidenceState(stage="found"),
    }

    updated = GameState.model_validate(
        {
            **state.model_dump(),
            "evidence": {
                key: value.model_dump() for key, value in next_evidence.items()
            },
            "score": progress.score + rule.score,
            "revision": state.revision + 1,
        }
    )

    return EvidenceCollectionResult(
        state=updated,
        created=True,
        progress=get_collection_progress(updated, evidence_rules),
    )
