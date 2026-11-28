"""이슈 #230 - 확장판 서버 전용 판정 원장 로더."""

import hashlib
import hmac
import json
import re

from pathlib import Path

from crimescene.chat.npc_persona import (
    EXPECTED_CHARACTER_IDS,
)
from crimescene.scenario.expanded_ending import (
    ExpandedCaseTruth,
)


MAX_TRUTH_FILE_SIZE = 256 * 1024

EXPECTED_CASE_ID = "CASE-001"
EXPECTED_CONTENT_VERSION = "case001_1120"
EXPECTED_ACCESS_SCOPE = "ENGINE_ONLY"


def reject_duplicate_keys(pairs):
    """중복 JSON 키를 통한 데이터 덮어쓰기를 차단한다."""

    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate truth field")

        result[key] = value

    return result


def load_expanded_case_truth(
    path: Path,
    *,
    expected_sha256: str,
) -> ExpandedCaseTruth:
    """신뢰된 승인 체크섬과 일치하는 서버 전용 원장을 로딩한다."""

    if not isinstance(path, Path):
        raise TypeError("Invalid truth path")

    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            expected_sha256,
        ) is None
    ):
        raise ValueError("Invalid approved truth checksum")

    if path.is_symlink():
        raise PermissionError("Invalid private truth file")

    if not path.is_file():
        raise FileNotFoundError(
            "Expanded private truth file unavailable"
        )

    # 과도하게 큰 원장 파일의 메모리 사용을 제한한다.
    with path.open("rb") as stream:
        raw = stream.read(MAX_TRUTH_FILE_SIZE + 1)

    if len(raw) > MAX_TRUTH_FILE_SIZE:
        raise ValueError("Expanded truth file too large")

    actual_sha256 = (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )

    if not hmac.compare_digest(
        actual_sha256,
        expected_sha256,
    ):
        raise PermissionError(
            "Expanded truth checksum mismatch"
        )

    try:
        text = raw.decode("utf-8-sig")

        payload = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
        )

        if not isinstance(payload, dict):
            raise ValueError("Invalid truth root")

        # 기본값에 의존하지 않고 명시적인 원장 범위를 검증한다.
        if (
            payload.get("case_id") != EXPECTED_CASE_ID
            or payload.get("content_version")
                != EXPECTED_CONTENT_VERSION
            or payload.get("access_scope")
                != EXPECTED_ACCESS_SCOPE
        ):
            raise ValueError("Invalid truth identity")

        truth = ExpandedCaseTruth.model_validate_json(
            text,
            strict=True,
        )

        if (
            truth.perpetrator_character_id
            not in EXPECTED_CHARACTER_IDS
        ):
            raise ValueError("Invalid truth character")

        for field in (
            truth.motive,
            truth.cause_of_death,
            truth.crime_method,
            truth.crime_event_id,
        ):
            if not field.strip():
                raise ValueError("Empty truth field")

    except (TypeError, ValueError, UnicodeError):
        # Pydantic 오류에 원본 사건 데이터가 포함될 수 있으므로
        # 외부에는 일반화된 오류만 전달한다.
        raise ValueError(
            "Invalid expanded private truth"
        ) from None

    return truth
