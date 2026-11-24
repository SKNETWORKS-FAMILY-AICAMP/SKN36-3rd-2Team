"""Issue #146 - 서버 전용 챕터 해금 규칙 로더."""

import json
from pathlib import Path
from types import MappingProxyType

from crimescene.scenario.chapter_progress import (
    CHAPTER_ORDER,
    ChapterUnlockRule,
)


def load_chapter_rules(
    path: Path,
) -> MappingProxyType[str, ChapterUnlockRule]:
    """승인된 서버 설정에서 챕터 해금 규칙을 로딩합니다."""

    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, dict):
        raise TypeError("챕터 설정은 JSON 객체여야 합니다.")

    if set(data) != {"case_id", "chapters"}:
        raise ValueError("챕터 설정 구조가 올바르지 않습니다.")

    if data["case_id"] != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    chapters = data["chapters"]

    if not isinstance(chapters, dict):
        raise TypeError("챕터 규칙 구조가 올바르지 않습니다.")

    if set(chapters) != set(CHAPTER_ORDER[1:]):
        raise ValueError("CH01~CH04 규칙이 모두 필요합니다.")

    required_fields = {
        "required_evidence",
        "required_flags",
        "required_presentations",
    }

    rules: dict[str, ChapterUnlockRule] = {}

    for chapter in CHAPTER_ORDER[1:]:
        raw = chapters[chapter]

        if (
            not isinstance(raw, dict)
            or set(raw) != required_fields
        ):
            raise ValueError("챕터 규칙 필드가 올바르지 않습니다.")

        for field in required_fields:
            values = raw[field]

            if (
                not isinstance(values, list)
                or any(
                    not isinstance(value, str)
                    for value in values
                )
                or len(values) != len(set(values))
            ):
                raise ValueError("챕터 조건이 올바르지 않습니다.")

        rules[chapter] = ChapterUnlockRule(
            target_chapter=chapter,
            required_evidence=frozenset(
                raw["required_evidence"]
            ),
            required_flags=frozenset(
                raw["required_flags"]
            ),
            required_presentations=frozenset(
                raw["required_presentations"]
            ),
        )

    return MappingProxyType(rules)