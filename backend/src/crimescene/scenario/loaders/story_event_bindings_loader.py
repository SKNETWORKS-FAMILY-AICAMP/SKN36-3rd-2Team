"""Issue #147 - 서버 전용 Story Event 바인딩 로더."""

import json
from pathlib import Path
from types import MappingProxyType

from crimescene.api.story_event_delivery_gate import StoryEventBinding


def load_story_event_bindings(
    path: Path,
) -> MappingProxyType[str, StoryEventBinding]:
    """승인된 서버 설정에서 이벤트 바인딩을 읽습니다."""

    data = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(data, dict):
        raise TypeError("이벤트 설정은 JSON 객체여야 합니다.")

    if set(data) != {"case_id", "bindings"}:
        raise ValueError("이벤트 설정 구조가 올바르지 않습니다.")

    if data["case_id"] != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    rows = data["bindings"]

    if not isinstance(rows, list):
        raise TypeError("이벤트 바인딩은 목록이어야 합니다.")

    if len(rows) > 30:
        raise ValueError("이벤트 바인딩 수가 너무 많습니다.")

    bindings: dict[str, StoryEventBinding] = {}
    source_ids: set[str] = set()

    required_fields = {
        "source_story_id",
        "event_key",
        "chapter",
    }

    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("이벤트 바인딩은 객체여야 합니다.")

        if set(row) != required_fields:
            raise ValueError("이벤트 바인딩 필드가 올바르지 않습니다.")

        binding = StoryEventBinding(
            source_story_id=row["source_story_id"],
            event_key=row["event_key"],
            chapter=row["chapter"],
        )

        # 하나의 원본 이벤트는 하나의 Django 이벤트에만 연결합니다.
        if binding.source_story_id in source_ids:
            raise ValueError("중복된 원본 Story ID입니다.")

        if binding.event_key in bindings:
            raise ValueError("중복된 Event Key입니다.")

        source_ids.add(binding.source_story_id)
        bindings[binding.event_key] = binding

    return MappingProxyType(bindings)