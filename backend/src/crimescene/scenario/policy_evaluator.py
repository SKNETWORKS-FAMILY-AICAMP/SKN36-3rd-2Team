from collections.abc import Iterable, Mapping

from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GamePhase, GameState


def matches_ending_requirement(
    required_ending: str | None,
    state: GameState,
) -> bool:
    if required_ending is None:
        return True

    if state.phase != GamePhase.FINISHED:
        return False

    if required_ending == "DEEP":
        return (
            state.outcome == "SUCCESS"
            and state.deep_eligible is True
        )

    return state.outcome == required_ending

class PolicyEvaluator:
    """CASE-001 접근 정책 판정 엔진.

    모든 필수 조건을 충족해야 접근을 허용한다.
    정책이 없거나 조건이 불명확하면 접근을 거부한다.
    """

    VALID_EVIDENCE_STAGES = frozenset({"found", "resolved"})

    def __init__(
        self,
        policies: Mapping[str, AccessPolicy],
    ) -> None:
        self._policies = dict(policies)

    def is_allowed(
        self,
        policy_id: str,
        state: GameState,
        *,
        active_character_id: str | None = None,
        matched_topics: Iterable[str] = (),
    ) -> bool:
        """현재 게임 상태에서 정책 접근 가능 여부를 판정한다."""

        # 1. 등록되지 않은 정책은 무조건 거부
        policy = self._policies.get(policy_id)

        if policy is None:
            return False

        # 2. NPC 접근 조건
        if policy.required_character is not None:
            if active_character_id != policy.required_character:
                return False

            if active_character_id not in state.unlocked_characters:
                return False

        # 3. 획득한 증거 확인
        collected_evidence = {
            evidence_id
            for evidence_id, evidence_state in state.evidence.items()
            if evidence_state.stage in self.VALID_EVIDENCE_STAGES
        }

        if not set(policy.required_evidence).issubset(collected_evidence):
            return False

        # 4. 증거 제시 조건
        # 정책: "C03:E05"
        # 상태: {"C03": ["E05"]}
        for presentation in policy.required_presentations:
            parts = presentation.split(":")

            if len(parts) != 2 or not all(parts):
                return False

            npc_id, evidence_id = parts

            # 실제로 획득하지 않은 증거는 제시 인정 불가
            if evidence_id not in collected_evidence:
                return False

            presented_evidence = state.presented.get(npc_id, [])

            if evidence_id not in presented_evidence:
                return False

        # 5. 게임 플래그 확인
        if not set(policy.required_flags).issubset(state.flags):
            return False

        # 6. 질문 주제 확인
        if not set(policy.required_topics).issubset(set(matched_topics)):
            return False

        # 7. 이전 공개 지식 카드 확인
        if not set(policy.required_disclosed_cards).issubset(state.disclosed_cards):
            return False

        # 8. 엔딩 조건 확인
        # 엔딩 조건이 없거나, 현재 엔딩과 일치해야 허용
        return matches_ending_requirement(policy.required_ending, state)