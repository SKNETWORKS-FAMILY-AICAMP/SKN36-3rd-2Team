"""Issue #28 - 증거 수집 및 NPC 해금 원자적 처리."""

from collections.abc import Mapping
from dataclasses import dataclass

from crimescene.scenario.evidence_collection import (
    CollectionProgress,
    collect_evidence,
)
from crimescene.scenario.npc_unlock import (
    NPCUnlockRule,
    find_unlockable_npcs,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@dataclass(frozen=True, slots=True)
class EvidenceServiceResult:
    """증거 획득 및 인물 해금 결과."""

    state: GameState
    created: bool
    unlocked_npcs: tuple[str, ...]
    progress: CollectionProgress


def collect_evidence_atomic(
    *,
    session_id: str,
    evidence_id: str,
    active_character_id: str,
    repository: SQLiteCase001Repository,
    evidence_rules: Mapping[str, EvidenceRule],
    acquisition_policy_ids: Mapping[str, str],
    evaluator: PolicyEvaluator,
    unlock_rules: Mapping[str, NPCUnlockRule],
) -> EvidenceServiceResult:
    """증거 획득과 NPC 해금을 검증 후 한 번에 저장합니다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("올바른 SQLite 저장소가 필요합니다.")

    if not isinstance(evidence_id, str):
        raise TypeError("증거 ID는 문자열이어야 합니다.")

    # 서버 DB에 저장된 최신 상태를 기준으로 처리합니다.
    state = repository.load_state(session_id)

    selection = repository.load_selection(session_id)

    if (
        selection is None
        or selection[0] != active_character_id
        or selection[1] != state.revision
    ):
        raise PermissionError("현재 선택된 NPC가 아닙니다.")

    rule = evidence_rules.get(evidence_id)

    # 증거 보유자가 아닌 NPC를 통한 획득을 차단합니다.
    if isinstance(rule, EvidenceRule) and rule.holder != active_character_id:
        raise PermissionError("해당 NPC가 보유한 증거가 아닙니다.")

    # 1. 증거 수집 조건 및 점수 검증
    collection = collect_evidence(
        state=state,
        evidence_id=evidence_id,
        evidence_rules=evidence_rules,
        acquisition_policy_ids=acquisition_policy_ids,
        evaluator=evaluator,
        active_character_id=active_character_id,
    )

    # 중복 수집은 상태와 revision을 변경하지 않습니다.
    if not collection.created:
        return EvidenceServiceResult(
            state=state,
            created=False,
            unlocked_npcs=(),
            progress=collection.progress,
        )

    # 2. 증거 획득 후 NPC 해금 조건 평가
    new_unlocks = find_unlockable_npcs(
        collection.state,
        unlock_rules,
    )

    # 3. 증거·점수·해금 정보를 하나의 상태로 구성
    updated = GameState.model_validate(
        {
            **collection.state.model_dump(),
            "unlocked_characters": [
                *collection.state.unlocked_characters,
                *new_unlocks,
            ],
        }
    )

    # 4. #27에서 구현한 원자적 저장 메서드 재사용
    committed = repository.commit_state(
        expected_state=state,
        updated_state=updated,
    )

    return EvidenceServiceResult(
        state=committed,
        created=True,
        unlocked_npcs=new_unlocks,
        progress=collection.progress,
    )
