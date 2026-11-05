from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.models import CaseMetadata, TimelineEvent


@dataclass(frozen=True, slots=True)
class IntegrityViolation:
    """사건 데이터 간 참조 오류."""

    path: str
    message: str


def validate_case_references(
    case: CaseMetadata,
    truth: CaseTruth,
    timeline: Sequence[TimelineEvent],
    *,
    person_ids: Collection[str] | None = None,
    location_ids: Collection[str] | None = None,
    evidence_ids: Collection[str] | None = None,
) -> list[IntegrityViolation]:
    """사건 기본 정보, 진실 원장, 타임라인의 참조 무결성을 검사한다.

    인물·장소·증거 ID 목록이 None이면 해당 종류의 참조 검사를 생략한다.
    실제 시나리오 데이터는 변경하지 않는다.
    """

    errors: list[IntegrityViolation] = []

    def add_error(path: str, message: str) -> None:
        errors.append(
            IntegrityViolation(
                path=path,
                message=message,
            )
        )

    # 1. 사건 ID 일치 여부
    if case.case_id != truth.case_id:
        add_error(
            "case_id",
            "사건 기본 정보와 진실 원장의 case_id가 다릅니다.",
        )

    # 2. 타임라인 이벤트 ID 중복 여부
    event_id_counts = Counter(event.event_id for event in timeline)

    for event_id, count in sorted(event_id_counts.items()):
        if count > 1:
            add_error(
                "timeline",
                f"중복된 event_id: {event_id}",
            )

    event_ids = set(event_id_counts)

    # 3. 실제 범행 이벤트 존재 여부
    if truth.crime_event_id not in event_ids:
        add_error(
            "truth.crime_event_id",
            f"존재하지 않는 범행 이벤트: {truth.crime_event_id}",
        )

    # 4. 진실 원장의 관련 사건 참조 검증
    for index, event_id in enumerate(truth.related_event_ids):
        if event_id not in event_ids:
            add_error(
                f"truth.related_event_ids[{index}]",
                f"존재하지 않는 이벤트: {event_id}",
            )

    # 5. 실제 범인 ID 검증
    if person_ids is not None:
        valid_person_ids = set(person_ids)

        if truth.perpetrator_character_id not in valid_person_ids:
            add_error(
                "truth.perpetrator_character_id",
                "범인 ID가 인물 목록에 존재하지 않습니다.",
            )

    else:
        valid_person_ids = None

    # 6. 장소 ID 검증 준비
    valid_location_ids = set(location_ids) if location_ids is not None else None

    # 7. 증거 ID 검증 준비
    valid_evidence_ids = set(evidence_ids) if evidence_ids is not None else None

    # 8. 진실 원장 참조 검사
    truth_references = [
        (
            "related_location_ids",
            truth.related_location_ids,
            valid_location_ids,
        ),
        (
            "related_evidence_ids",
            truth.related_evidence_ids,
            valid_evidence_ids,
        ),
    ]

    for field_name, references, valid_ids in truth_references:
        if valid_ids is None:
            continue

        for index, reference_id in enumerate(references):
            if reference_id not in valid_ids:
                add_error(
                    f"truth.{field_name}[{index}]",
                    f"존재하지 않는 참조 ID: {reference_id}",
                )

    # 9. 타임라인에 연결된 인물·장소·증거 검증
    for event_index, event in enumerate(timeline):
        event_references = [
            ("actor_ids", event.actor_ids, valid_person_ids),
            ("location_ids", event.location_ids, valid_location_ids),
            ("evidence_ids", event.evidence_ids, valid_evidence_ids),
        ]

        for field_name, references, valid_ids in event_references:
            if valid_ids is None:
                continue

            for reference_index, reference_id in enumerate(references):
                if reference_id not in valid_ids:
                    add_error(
                        (f"timeline[{event_index}].{field_name}[{reference_index}]"),
                        f"존재하지 않는 참조 ID: {reference_id}",
                    )

    return errors
