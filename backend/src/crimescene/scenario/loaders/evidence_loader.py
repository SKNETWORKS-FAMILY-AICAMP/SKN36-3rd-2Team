import json
from pathlib import Path

from pydantic import ValidationError

from crimescene.scenario.schemas.evidence import (
    EvidenceCatalog,
    EvidenceRule,
)


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """JSON 객체에서 중복된 Key를 탐지한다."""

    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복된 JSON Key: {key}")

        result[key] = value

    return result


def load_evidence_rules(
    path: Path,
) -> dict[str, EvidenceRule]:
    """증거 규칙 JSON 파일을 읽고 검증한다.

    검증 항목:
    - JSON 형식
    - 중복 Key
    - 증거 ID 형식
    - Pydantic 스키마
    - 빈 증거 목록
    """

    # 1. JSON 파일 읽기
    try:
        data = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"증거 규칙 JSON 파싱 실패: {path}") from exc

    # 2. Pydantic 검증
    try:
        catalog = EvidenceCatalog.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"증거 규칙 스키마 검증 실패: {path}") from exc

    # 3. 빈 증거 목록 검사
    if not catalog.root:
        raise ValueError(f"증거 규칙이 비어 있습니다: {path}")

    return catalog.root
