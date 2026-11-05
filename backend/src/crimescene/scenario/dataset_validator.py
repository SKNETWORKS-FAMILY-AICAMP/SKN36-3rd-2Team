from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.integrity import (
    IntegrityViolation,
    validate_case_references,
)
from crimescene.scenario.json_loader import (
    load_case_metadata,
    load_engine_timeline,
)


@dataclass(frozen=True)
class ScenarioValidationReport:
    """사건 데이터 통합 검증 결과."""

    status: Literal["PENDING", "INVALID", "PARTIAL", "VALID"]

    missing_files: tuple[str, ...] = ()
    violations: tuple[IntegrityViolation, ...] = ()
    unchecked_id_types: tuple[str, ...] = ()

    event_count: int = 0


def validate_scenario_data(
    root: Path,
    *,
    person_ids: Collection[str] | None = None,
    location_ids: Collection[str] | None = None,
    evidence_ids: Collection[str] | None = None,
) -> ScenarioValidationReport:
    """사건 JSON 데이터를 읽고 참조 무결성을 검증한다."""

    # 1. 파일 경로 설정
    metadata_path = root / "public" / "case_metadata.json"

    truth_path = root / "engine_only" / "case_truth.json"

    timeline_path = root / "engine_only" / "timeline.json"

    required_files = (
        metadata_path,
        truth_path,
        timeline_path,
    )

    # 2. 필수 파일 존재 여부 확인
    missing_files = tuple(
        path.relative_to(root).as_posix()
        for path in required_files
        if not path.is_file()
    )

    # 3. 사건 기본 정보 검증
    if metadata_path.is_file():
        case = load_case_metadata(metadata_path)
    else:
        case = None

    # 4. 미완성 데이터 처리
    if missing_files:
        return ScenarioValidationReport(
            status="PENDING",
            missing_files=missing_files,
        )

    # 모든 필수 파일이 존재하면 사건 정보를 로딩한다.
    if case is None:
        raise ValueError("사건 기본 정보를 불러올 수 없습니다.")

    # 5. 관리자 전용 진실 원장 로딩
    truth = CaseTruth.model_validate_json(truth_path.read_text(encoding="utf-8"))

    # 6. 사건 타임라인 로딩
    timeline = load_engine_timeline(timeline_path)

    # 7. 참조 무결성 검사
    violations = tuple(
        validate_case_references(
            case,
            truth,
            timeline,
            person_ids=person_ids,
            location_ids=location_ids,
            evidence_ids=evidence_ids,
        )
    )

    # 8. 아직 검증하지 못한 참조 유형 확인
    unchecked = tuple(
        name
        for name, ids in (
            ("person_ids", person_ids),
            ("location_ids", location_ids),
            ("evidence_ids", evidence_ids),
        )
        if ids is None
    )

    # 9. 최종 상태 결정
    if violations:
        status = "INVALID"
    elif unchecked:
        status = "PARTIAL"
    else:
        status = "VALID"

    return ScenarioValidationReport(
        status=status,
        violations=violations,
        unchecked_id_types=unchecked,
        event_count=len(timeline),
    )
