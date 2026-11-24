
"""Issue #145 - 서버 GameState 기반 읽기 전용 Story Context."""

from collections.abc import Mapping
from dataclasses import dataclass

from crimescene.api.django_content_client import (
    ContentServiceNotFoundError,
)
from crimescene.api.story_event_delivery_gate import (
    StoryEventBinding,
    select_approved_queued_story_event,
)
from crimescene.api.story_event_delivery_service import (
    ApprovedEventFetcher,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@dataclass(frozen=True, slots=True)
class StoryContext:
    """서버 내부에서 사용하는 불변 게임 진행 스냅샷."""

    case_id: str
    session_id: str
    revision: int
    phase: GamePhase
    current_chapter: ChapterCode
    unlocked_chapters: tuple[ChapterCode, ...]
    unlocked_characters: tuple[str, ...]
    collected_evidence_ids: tuple[str, ...]
    presented_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    disclosed_card_ids: tuple[str, ...]
    flags: tuple[str, ...]
    can_investigate: bool

    def get_presented_evidence(
        self,
        character_id: str,
    ) -> tuple[str, ...]:
        """특정 NPC에게 제시한 증거만 반환합니다."""
        for npc_id, evidence_ids in self.presented_evidence:
            if npc_id == character_id:
                return evidence_ids

        return ()


class StoryContextService:
    """서버 저장소에서 검증된 진행 맥락을 읽기 전용으로 구성합니다."""

    def __init__(
        self,
        repository: SQLiteCase001Repository,
    ) -> None:
        if not isinstance(repository, SQLiteCase001Repository):
            raise TypeError("게임 상태 저장소가 필요합니다.")

        self._repository = repository

    def load(
        self,
        session_id: str,
        *,
        expected_revision: int,
    ) -> StoryContext:
        """소유권 검증을 완료한 서버 호출 경로에서만 사용합니다."""

        if not isinstance(session_id, str):
            raise TypeError("세션 ID는 문자열이어야 합니다.")

        if not session_id.strip() or len(session_id) > 128:
            raise ValueError("유효하지 않은 세션 ID입니다.")

        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise TypeError("revision은 정수여야 합니다.")

        if expected_revision < 0:
            raise ValueError("revision은 0 이상이어야 합니다.")

        # 클라이언트가 제공한 GameState를 사용하지 않습니다.
        state = self._repository.load_state(session_id)

        if state.case_id != "CASE-001":
            raise ValueError("지원하지 않는 사건입니다.")

        if state.session_id != session_id:
            raise PermissionError("세션 정보가 일치하지 않습니다.")

        if state.revision != expected_revision:
            raise ValueError("GameState revision이 일치하지 않습니다.")

        # 기존 접근 정책과 동일한 증거 획득 기준을 적용합니다.
        collected = {
            evidence_id
            for evidence_id, evidence in state.evidence.items()
            if evidence.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
        }

        unlocked_characters = set(state.unlocked_characters)

        # 미획득 증거와 잠긴 NPC의 제시 기록을 제외합니다.
        presented = tuple(
            (
                character_id,
                tuple(sorted(set(evidence_ids) & collected)),
            )
            for character_id, evidence_ids in sorted(
                state.presented.items()
            )
            if character_id in unlocked_characters
            and collected.intersection(evidence_ids)
        )

        return StoryContext(
            case_id=state.case_id,
            session_id=state.session_id,
            revision=state.revision,
            phase=state.phase,
            current_chapter=state.current_chapter,
            unlocked_chapters=tuple(state.unlocked_chapters),
            unlocked_characters=tuple(sorted(unlocked_characters)),
            collected_evidence_ids=tuple(sorted(collected)),
            presented_evidence=presented,
            disclosed_card_ids=tuple(
                sorted(set(state.disclosed_cards))
            ),
            flags=tuple(sorted(set(state.flags))),
            can_investigate=(
                state.phase == GamePhase.INVESTIGATION
                and state.outcome in (None, "ONGOING")
            ),
        )


    def load_pending_event_keys(
        self,
        session_id: str,
        *,
        expected_revision: int,
        bindings: Mapping[str, StoryEventBinding],
        fetch_approved_event: ApprovedEventFetcher,
    ) -> tuple[str, ...]:
        """현재 플레이어에게 공개 가능한 미확인 이벤트 ID를 반환합니다."""

        context = self.load(
            session_id,
            expected_revision=expected_revision,
        )

        if not isinstance(bindings, Mapping) or len(bindings) > 30:
            raise ValueError("잘못된 스토리 이벤트 바인딩입니다.")

        if not callable(fetch_approved_event):
            raise TypeError("승인 콘텐츠 조회 함수가 필요합니다.")

        source_ids: set[str] = set()

        for event_key, binding in bindings.items():
            if (
                not isinstance(binding, StoryEventBinding)
                or binding.event_key != event_key
                or binding.source_story_id in source_ids
            ):
                raise ValueError("잘못된 스토리 이벤트 바인딩입니다.")

            source_ids.add(binding.source_story_id)

        if not context.can_investigate:
            return ()

        state = self._repository.load_state(session_id)

        if state.revision != expected_revision:
            raise ValueError("GameState revision이 일치하지 않습니다.")

        queued = set(state.queued_story_events)
        acknowledged = set(state.acknowledged_story_events)

        pending = []

        for event_key, binding in sorted(bindings.items()):
            if (
                binding.source_story_id not in queued
                or binding.source_story_id in acknowledged
                or binding.chapter != state.current_chapter
            ):
                continue

            try:
                approved = fetch_approved_event(event_key)
            except ContentServiceNotFoundError:
                # 미승인 또는 존재하지 않는 콘텐츠는 제외합니다.
                continue

            event = select_approved_queued_story_event(
                state=state,
                binding=binding,
                approved_event=approved,
            )

            if event is not None:
                pending.append(event.event_key)

        # 외부 콘텐츠 조회 중 게임 상태가 변경되었는지 확인합니다.
        latest = self._repository.load_state(session_id)

        if latest != state:
            raise ValueError("GameState revision이 일치하지 않습니다.")

        return tuple(pending)
