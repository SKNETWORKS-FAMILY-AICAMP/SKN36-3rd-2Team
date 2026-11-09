"""Issue #28 - NPC 해금 조건 판정 엔진."""

from collections.abc import Mapping
from dataclasses import dataclass

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState


@dataclass(frozen=True, slots=True)
class NPCUnlockRule:
    """서버에서 관리하는 NPC 해금 조건."""

    required_evidence: frozenset[str] = frozenset()
    required_flags: frozenset[str] = frozenset()
    required_disclosed_cards: frozenset[str] = frozenset()
    required_presentations: frozenset[str] = frozenset()


def find_unlockable_npcs(
    state: GameState,
    rules: Mapping[str, NPCUnlockRule],
) -> tuple[str, ...]:
    """현재 GameState에서 새롭게 해금 가능한 NPC를 반환합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    if not isinstance(rules, Mapping):
        raise TypeError("해금 규칙은 매핑이어야 합니다.")

    if state.outcome not in (None, "ONGOING"):
        return ()

    collected = {
        evidence_id
        for evidence_id, evidence in state.evidence.items()
        if evidence.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
    }

    unlocked = set(state.unlocked_characters)
    flags = set(state.flags)
    disclosed = set(state.disclosed_cards)

    new_unlocks = []

    for npc_id, rule in sorted(rules.items()):
        if npc_id not in EXPECTED_CHARACTER_IDS:
            raise ValueError(f"등록되지 않은 NPC입니다: {npc_id}")

        if not isinstance(rule, NPCUnlockRule):
            raise TypeError("NPC 해금 규칙 타입이 올바르지 않습니다.")

        # 조건이 없는 규칙은 자동 해금하지 않습니다.
        if not any(
            (
                rule.required_evidence,
                rule.required_flags,
                rule.required_disclosed_cards,
                rule.required_presentations,
            )
        ):
            raise ValueError("해금 조건이 비어 있습니다.")

        if npc_id in unlocked:
            continue

        if not rule.required_evidence.issubset(collected):
            continue

        if not rule.required_flags.issubset(flags):
            continue

        if not rule.required_disclosed_cards.issubset(disclosed):
            continue

        presentations_valid = True

        for presentation in rule.required_presentations:
            parts = presentation.split(":")

            if len(parts) != 2 or not all(parts):
                presentations_valid = False
                break

            character_id, evidence_id = parts

            if evidence_id not in collected or evidence_id not in state.presented.get(
                character_id, []
            ):
                presentations_valid = False
                break

        if not presentations_valid:
            continue

        new_unlocks.append(npc_id)

    return tuple(new_unlocks)
