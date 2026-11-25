"""Issue #147 - 게임 진행 기반 Story Event 큐 구성."""

from collections.abc import Callable, Mapping

from crimescene.api.django_content_client import (
    ApprovedStoryEvent,
    ContentServiceError,
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_conditions import (
    StoryEventConditions,
    matches_story_event_prerequisites,
)
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
    select_approved_queued_story_event,
)
from crimescene.scenario.schemas.game_state import GameState


def stage_story_events(
    state: GameState,
    *,
    bindings: Mapping[str, StoryEventBinding],
    conditions: Mapping[str, StoryEventConditions],
    fetch_approved_event: Callable[[str], ApprovedStoryEvent],
) -> GameState:
    """승인된 이벤트를 저장 예정 상태에 추가합니다.

    DB 저장과 revision 증가는 호출자가 담당합니다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(bindings, Mapping):
        raise TypeError("이벤트 바인딩은 매핑이어야 합니다.")

    if not isinstance(conditions, Mapping):
        raise TypeError("이벤트 조건은 매핑이어야 합니다.")

    if not callable(fetch_approved_event):
        raise TypeError("승인 이벤트 조회 함수가 필요합니다.")

    if len(bindings) > 30 or len(conditions) > 30:
        raise ValueError("이벤트 설정 수가 너무 많습니다.")

    source_ids: set[str] = set()

    # 전체 설정을 먼저 검증합니다.
    for event_key, binding in bindings.items():
        if not isinstance(binding, StoryEventBinding):
            raise TypeError("올바르지 않은 이벤트 바인딩입니다.")

        if binding.event_key != event_key:
            raise ValueError("Event Key가 일치하지 않습니다.")

        if binding.source_story_id in source_ids:
            raise ValueError("중복된 Story ID입니다.")

        source_ids.add(binding.source_story_id)

        rule = conditions.get(binding.source_story_id)

        if rule is None:
            raise ValueError("서버 이벤트 조건이 등록되지 않았습니다.")

        if not isinstance(rule, StoryEventConditions):
            raise TypeError("이벤트 조건의 자료형이 올바르지 않습니다.")

        if (
            rule.story_id != binding.source_story_id
            or rule.chapter != binding.chapter
        ):
            raise ValueError("이벤트 조건과 바인딩이 일치하지 않습니다.")

    if set(conditions) != source_ids:
        raise ValueError("이벤트 조건 목록이 일치하지 않습니다.")

    updated = state

    for event_key, binding in sorted(bindings.items()):
        source_id = binding.source_story_id

        # 기존 큐 및 ACK 이력을 유지합니다.
        if source_id in updated.queued_story_events:
            continue

        rule = conditions[source_id]

        # 기존 서버 조건 평가 엔진을 재사용합니다.
        if not matches_story_event_prerequisites(
            rule,
            updated,
        ):
            continue

        try:
            approved = fetch_approved_event(event_key)

        except ContentServiceNotFoundError:
            if source_id == "STORY_026":
                raise ContentServiceError(
                    "Required story event approval unavailable"
                ) from None

            # 미승인 또는 미게시 콘텐츠는 큐에 추가하지 않습니다.
            continue

        # 기존 객체를 변경하지 않고 검증용 후보를 생성합니다.
        if source_id == "STORY_026":
            if (
                not isinstance(approved, ApprovedStoryEvent)
                or approved.event_key != event_key
                or approved.chapter != "CH03"
                or set(approved.required_evidence_ids) != {"E20", "E26"}
            ):
                raise ContentServiceError(
                    "Invalid STORY_026 approval contract"
                )

        candidate = GameState.model_validate(
            {
                **updated.model_dump(mode="python"),
                "queued_story_events": [
                    *updated.queued_story_events,
                    source_id,
                ],
            }
        )

        # Django 승인, 챕터, 필수 증거 조건을 재검증합니다.
        allowed = select_approved_queued_story_event(
            state=candidate,
            binding=binding,
            approved_event=approved,
        )

        if allowed is not None:
            updated = candidate
        elif source_id == "STORY_026":
            raise ContentServiceError(
                "Required story event delivery denied"
            )

    return updated