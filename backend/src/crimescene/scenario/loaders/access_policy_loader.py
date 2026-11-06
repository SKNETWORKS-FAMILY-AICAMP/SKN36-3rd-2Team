import json
from pathlib import Path

from pydantic import ValidationError

from crimescene.scenario.schemas.access_policy import (
    AccessPolicy,
    AccessPolicyCatalog,
)


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """JSON 객체의 중복 Key를 탐지한다."""

    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복된 JSON Key: {key}")

        result[key] = value

    return result


def load_access_policies(
    path: Path,
) -> dict[str, AccessPolicy]:
    """v7.1 접근 정책 JSON 파일을 읽고 검증한다.

    검증 항목:
    - JSON 형식
    - 중복 JSON Key
    - 정책 ID 형식
    - Pydantic 스키마
    - 빈 정책 목록
    - 예상하지 못한 최상위 항목
    """

    # 1. JSON 로딩
    try:
        content = path.read_text(encoding="utf-8-sig")

        data = json.loads(
            content,
            object_pairs_hook=_reject_duplicate_keys,
        )

    except json.JSONDecodeError as exc:
        raise ValueError(f"접근 정책 JSON 파싱 실패: {path}") from exc

    # 2. 최상위 구조 검사
    if not isinstance(data, dict):
        raise TypeError("접근 정책 데이터는 JSON 객체여야 합니다.")
    # 3. 빈 정책 목록 검사
    if not data:
        raise ValueError(f"접근 정책이 비어 있습니다: {path}")

    # 4. 예상하지 못한 항목 탐지
    unexpected_keys = [key for key in data if not key.startswith("POL-")]

    if unexpected_keys:
        raise ValueError(f"정책이 아닌 최상위 항목이 존재합니다: {unexpected_keys}")

    # 5. Pydantic 스키마 검증
    try:
        catalog = AccessPolicyCatalog.model_validate(data)

    except ValidationError as exc:
        raise ValueError(f"접근 정책 스키마 검증 실패: {path}") from exc

    return catalog.root
