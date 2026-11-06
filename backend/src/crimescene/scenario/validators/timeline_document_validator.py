from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from crimescene.scenario.integrity import IntegrityViolation
from crimescene.scenario.schemas.document import PlayerDocument


def validate_timeline_document_metadata(
    documents: Sequence[PlayerDocument],
    timeline: Sequence[Mapping[str, Any]],
    *,
    case_id: str,
) -> list[IntegrityViolation]:
    """v7.1 타임라인과 플레이어 문서의 메타데이터를 검증한다.

    관리자 전용 사건 정보를 플레이어 문서에 병합하지 않는다.
    """

    errors: list[IntegrityViolation] = []

    def add_error(path: str, message: str) -> None:
        errors.append(
            IntegrityViolation(
                path=path,
                message=message,
            )
        )

    def check_source_refs(
        refs: object,
        path: str,
    ) -> None:
        """출처 참조의 기본 구조를 검증한다."""

        if not isinstance(refs, list) or not refs:
            add_error(path, "출처 참조가 비어 있거나 목록이 아닙니다.")
            return

        for index, ref in enumerate(refs):
            item_path = f"{path}[{index}]"

            if not isinstance(ref, dict):
                add_error(
                    item_path,
                    "출처 참조는 객체여야 합니다.",
                )
                continue

            source_path = ref.get("path")

            if not isinstance(source_path, str) or not source_path.strip():
                add_error(
                    f"{item_path}.path",
                    "출처 파일 경로가 없습니다.",
                )

    # 1. 타임라인 이벤트 ID 중복 검사
    event_ids = [event.get("event_id") for event in timeline]

    counts = Counter(event_ids)

    for event_id, count in counts.items():
        if count > 1:
            add_error(
                "timeline",
                f"중복된 이벤트 ID: {event_id}",
            )

    # 2. 타임라인 데이터 검증
    for index, event in enumerate(timeline):
        prefix = f"timeline[{index}]"

        event_id = event.get("event_id")

        if not isinstance(event_id, str) or not event_id.strip():
            add_error(
                f"{prefix}.event_id",
                "이벤트 ID가 없습니다.",
            )

        if event.get("case_id") != case_id:
            add_error(
                f"{prefix}.case_id",
                "타임라인 사건 ID가 일치하지 않습니다.",
            )

        # 타임라인은 관리자 전용이어야 함
        if event.get("access_scope") != "admin_only":
            add_error(
                f"{prefix}.access_scope",
                "타임라인은 admin_only여야 합니다.",
            )

        # 사건 연도 검사
        year = event.get("incident_year")

        if type(year) is not int:
            add_error(
                f"{prefix}.incident_year",
                "사건 연도는 정수여야 합니다.",
            )

        # 원본 출처 검사
        check_source_refs(
            event.get("source_refs"),
            f"{prefix}.source_refs",
        )

    # 3. 플레이어 문서 검증
    for index, document in enumerate(documents):
        prefix = f"documents[{index}]"

        if document.case_id != case_id:
            add_error(
                f"{prefix}.case_id",
                "문서 사건 ID가 일치하지 않습니다.",
            )

        # 명시된 발생 연도와 연도 목록 비교
        if (
            document.incident_year is not None
            and document.incident_year not in document.incident_years
        ):
            add_error(
                f"{prefix}.incident_year",
                "문서 발생 연도가 incident_years에 없습니다.",
            )

        # incident_years는 문서와 관련된 연도 목록이다.
        # 모든 연도가 관리자 타임라인에 존재해야 하는 것은 아니다.

        # 문서 출처 검사
        check_source_refs(
            document.source_refs,
            f"{prefix}.source_refs",
        )

    return errors
