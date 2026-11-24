"""Issue #147 - 서버 전용 이벤트 발생 조건 로더."""

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from crimescene.api.story_event_conditions import StoryEventConditions
from crimescene.api.story_event_delivery_gate import StoryEventBinding


def load_story_event_conditions(
    path: Path,
    *,
    bindings: Mapping[str, StoryEventBinding],
) -> MappingProxyType[str, StoryEventConditions]:
    """이벤트 발생 조건과 기존 바인딩의 정합성을 검증합니다."""

    data = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(data, dict):
        raise TypeError("이벤트 설정은 객체여야 합니다.")

    if set(data) != {"case_id", "conditions"}:
        raise ValueError("이벤트 설정 구조가 올바르지 않습니다.")

    if data["case_id"] != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    rows = data["conditions"]

    if not isinstance(rows, list):
        raise TypeError("이벤트 조건은 목록이어야 합니다.")

    if len(rows) > 30:
        raise ValueError("이벤트 조건 수가 너무 많습니다.")

    required_fields = {
        "story_id",
        "chapter",
        "all_evidence",
        "any_evidence",
        "required_flags",
    }

    conditions: dict[str, StoryEventConditions] = {}

    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("이벤트 조건은 객체여야 합니다.")

        if set(row) != required_fields:
            raise ValueError("이벤트 조건 필드가 올바르지 않습니다.")

        for field in (
            "all_evidence",
            "any_evidence",
            "required_flags",
        ):
            values = row[field]

            if (
                not isinstance(values, list)
                or any(
                    not isinstance(value, str)
                    for value in values
                )
                or len(values) != len(set(values))
            ):
                raise ValueError("이벤트 조건 값이 올바르지 않습니다.")

        rule = StoryEventConditions(
            story_id=row["story_id"],
            chapter=row["chapter"],
            all_evidence=frozenset(row["all_evidence"]),
            any_evidence=frozenset(row["any_evidence"]),
            required_flags=frozenset(row["required_flags"]),
        )

        if rule.story_id in conditions:
            raise ValueError("중복된 이벤트 조건입니다.")

        conditions[rule.story_id] = rule

    expected_ids = {
        binding.source_story_id
        for binding in bindings.values()
    }

    if set(conditions) != expected_ids:
        raise ValueError("바인딩과 이벤트 조건 목록이 일치하지 않습니다.")

    for binding in bindings.values():
        rule = conditions[binding.source_story_id]

        if rule.chapter != binding.chapter:
            raise ValueError("이벤트 챕터가 일치하지 않습니다.")

    return MappingProxyType(conditions)