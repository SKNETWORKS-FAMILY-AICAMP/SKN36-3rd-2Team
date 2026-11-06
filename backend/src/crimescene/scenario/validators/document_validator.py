from collections.abc import Collection, Mapping, Sequence

from crimescene.scenario.integrity import IntegrityViolation
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule


def validate_document_evidence_references(
    documents: Sequence[PlayerDocument],
    evidence_rules: Mapping[str, EvidenceRule],
    *,
    case_id: str,
    character_ids: Collection[str],
    source_ids: Collection[str],
    flag_ids: Collection[str],
) -> list[IntegrityViolation]:
    """문서·증거·NPC·출처·플래그 참조 무결성을 검증한다."""

    errors: list[IntegrityViolation] = []

    valid_evidence = set(evidence_rules)
    valid_characters = set(character_ids)
    valid_sources = set(source_ids)
    valid_flags = set(flag_ids)

    def add_error(path: str, message: str) -> None:
        errors.append(
            IntegrityViolation(
                path=path,
                message=message,
            )
        )

    def check_ids(
        values: Sequence[str],
        valid_ids: set[str],
        path: str,
        label: str,
    ) -> None:
        """일반 ID 참조의 존재 여부를 검증한다."""

        for index, value in enumerate(values):
            if value not in valid_ids:
                add_error(
                    f"{path}[{index}]",
                    f"존재하지 않는 {label}: {value}",
                )

    def check_presentations(
        values: Sequence[str],
        path: str,
    ) -> None:
        """NPC:증거 형태의 제시 조건을 검증한다."""

        for index, value in enumerate(values):
            item_path = f"{path}[{index}]"

            parts = value.split(":")

            if len(parts) != 2 or not all(parts):
                add_error(
                    item_path,
                    f"잘못된 증거 제시 조건 형식: {value}",
                )
                continue

            character_id, evidence_id = parts

            if character_id not in valid_characters:
                add_error(
                    item_path,
                    f"존재하지 않는 NPC: {character_id}",
                )

            if evidence_id not in valid_evidence:
                add_error(
                    item_path,
                    f"존재하지 않는 증거: {evidence_id}",
                )

    # 1. 플레이어 문서 검증
    seen_doc_ids: set[str] = set()

    for index, document in enumerate(documents):
        prefix = f"documents[{index}]"

        # 사건 ID
        if document.case_id != case_id:
            add_error(
                f"{prefix}.case_id",
                "문서의 사건 ID가 일치하지 않습니다.",
            )

        # 문서 ID 중복
        if document.doc_id in seen_doc_ids:
            add_error(
                f"{prefix}.doc_id",
                f"중복된 문서 ID: {document.doc_id}",
            )

        seen_doc_ids.add(document.doc_id)

        # 문서가 참조하는 증거
        check_ids(
            document.source_evidence_ids,
            valid_evidence,
            f"{prefix}.source_evidence_ids",
            "증거",
        )

        # 문서 공개에 필요한 증거
        check_ids(
            document.required_evidence,
            valid_evidence,
            f"{prefix}.required_evidence",
            "필수 증거",
        )

        # 문서를 알고 있는 NPC
        check_ids(
            document.known_by_character_ids,
            valid_characters,
            f"{prefix}.known_by_character_ids",
            "인물",
        )

        # 원본 출처 문서
        check_ids(
            document.source_doc_ids,
            valid_sources,
            f"{prefix}.source_doc_ids",
            "출처 문서",
        )

        # 필수 게임 플래그
        check_ids(
            document.required_flags,
            valid_flags,
            f"{prefix}.required_flags",
            "게임 플래그",
        )

        # 증거 제시 조건
        check_presentations(
            document.required_presentations,
            f"{prefix}.required_presentations",
        )

    # 2. 증거 규칙 검증
    for evidence_id, rule in evidence_rules.items():
        prefix = f"evidence_rules[{evidence_id}]"

        # 증거 획득 선행 조건
        check_ids(
            rule.prerequisites,
            valid_evidence,
            f"{prefix}.prerequisites",
            "선행 증거",
        )

        # 증거 제시 조건
        check_presentations(
            rule.presentation,
            f"{prefix}.presentation",
        )

    return errors
