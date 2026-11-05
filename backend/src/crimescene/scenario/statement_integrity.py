from collections import Counter
from collections.abc import Collection, Sequence

from crimescene.scenario.integrity import IntegrityViolation
from crimescene.scenario.models import CaseMetadata, TimelineEvent
from crimescene.scenario.npc_knowledge import NPCKnowledgeCard
from crimescene.scenario.statement_assessment import StatementAssessment


def validate_statement_references(
    case: CaseMetadata,
    timeline: Sequence[TimelineEvent],
    knowledge_cards: Sequence[NPCKnowledgeCard],
    assessments: Sequence[StatementAssessment],
    *,
    person_ids: Collection[str] | None = None,
) -> list[IntegrityViolation]:
    """NPC 지식, 진술 평가, 사건 타임라인의 참조 무결성을 검사한다."""

    errors: list[IntegrityViolation] = []

    def add_error(path: str, message: str) -> None:
        errors.append(
            IntegrityViolation(
                path=path,
                message=message,
            )
        )

    # 1. 유효한 참조 ID 목록 구성
    event_ids = {event.event_id for event in timeline}

    valid_person_ids = set(person_ids) if person_ids is not None else None

    # 2. 지식 카드 ID 중복 검사
    knowledge_counts = Counter(card.knowledge_id for card in knowledge_cards)

    for knowledge_id, count in sorted(knowledge_counts.items()):
        if count > 1:
            add_error(
                "knowledge_cards",
                f"중복된 knowledge_id: {knowledge_id}",
            )

    knowledge_by_id = {card.knowledge_id: card for card in knowledge_cards}

    # 3. 진술 평가 ID 중복 검사
    assessment_counts = Counter(assessment.assessment_id for assessment in assessments)

    for assessment_id, count in sorted(assessment_counts.items()):
        if count > 1:
            add_error(
                "assessments",
                f"중복된 assessment_id: {assessment_id}",
            )

    # 4. NPC 지식 카드 소유자 검사
    for index, card in enumerate(knowledge_cards):
        if valid_person_ids is not None and card.npc_id not in valid_person_ids:
            add_error(
                f"knowledge_cards[{index}].npc_id",
                f"존재하지 않는 NPC ID: {card.npc_id}",
            )

    # 5. 진술 평가 참조 검사
    for index, assessment in enumerate(assessments):
        # 사건 ID 일치 여부
        if assessment.case_id != case.case_id:
            add_error(
                f"assessments[{index}].case_id",
                "진술 평가의 사건 ID가 일치하지 않습니다.",
            )

        # NPC 존재 여부
        if valid_person_ids is not None and assessment.npc_id not in valid_person_ids:
            add_error(
                f"assessments[{index}].npc_id",
                f"존재하지 않는 NPC ID: {assessment.npc_id}",
            )

        # 지식 카드 존재 여부
        knowledge = knowledge_by_id.get(assessment.knowledge_id)

        if knowledge is None:
            add_error(
                f"assessments[{index}].knowledge_id",
                f"존재하지 않는 지식 카드: {assessment.knowledge_id}",
            )

        elif knowledge_counts[assessment.knowledge_id] > 1:
            add_error(
                f"assessments[{index}].knowledge_id",
                "중복된 지식 카드 ID로 소유자를 확인할 수 없습니다.",
            )

        # 지식 소유자와 진술자 일치 여부
        elif knowledge.npc_id != assessment.npc_id:
            add_error(
                f"assessments[{index}].npc_id",
                "진술자와 지식 카드 소유자가 일치하지 않습니다.",
            )

        # 타임라인 이벤트 존재 여부
        for event_index, event_id in enumerate(assessment.related_event_ids):
            if event_id not in event_ids:
                add_error(
                    (f"assessments[{index}].related_event_ids[{event_index}]"),
                    f"존재하지 않는 이벤트: {event_id}",
                )

    return errors
