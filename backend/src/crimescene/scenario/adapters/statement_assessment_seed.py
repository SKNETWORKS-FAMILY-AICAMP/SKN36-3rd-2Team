from collections.abc import Sequence

from crimescene.scenario.schemas.character import CharacterProfile
from crimescene.scenario.statement_assessment import (
    StatementAssessment,
    StatementIntent,
    StatementTruthStatus,
)


def build_statement_assessment_seeds(
    characters: Sequence[CharacterProfile],
    *,
    case_id: str,
) -> list[StatementAssessment]:
    """NPC 주장에 대한 관리자 전용 평가 초기값을 생성한다.

    실제 사실 여부와 기만 의도는 추측하지 않는다.
    관리자 원장으로 확인된 경우에만 이후 확정한다.
    """

    assessments: list[StatementAssessment] = []

    for character in characters:
        for card in character.cards:
            if card.stance != "character_claim":
                continue

            assessment = StatementAssessment(
                assessment_id=f"AST-{card.id}",
                case_id=case_id,
                npc_id=character.id,
                knowledge_id=card.id,
                truth_status=StatementTruthStatus.UNVERIFIED,
                statement_intent=StatementIntent.UNKNOWN,
                related_event_ids=[],
                source_refs=[],
                access_scope="ENGINE_ONLY",
            )

            assessments.append(assessment)

    return assessments
