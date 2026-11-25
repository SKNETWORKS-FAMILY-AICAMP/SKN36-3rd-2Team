"""CASE-001 서버 측 챕터 해금 및 전환 엔진."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

CHAPTER_ORDER: tuple[ChapterCode, ...] = (
    "CH00",
    "CH01",
    "CH02",
    "CH03",
    "CH04",
)

VALID_EVIDENCE_STAGES = frozenset({"found", "resolved"})


@dataclass(frozen=True, slots=True)
class ChapterUnlockRule:
    """서버에서만 등록하는 챕터 해금 조건."""

    target_chapter: ChapterCode
    required_evidence: frozenset[str] = field(default_factory=frozenset)
    required_flags: frozenset[str] = field(default_factory=frozenset)
    required_presentations: frozenset[str] = field(default_factory=frozenset)
    requires_completed_prologue: bool = False

    def __post_init__(self):
        if self.target_chapter not in CHAPTER_ORDER[1:]:
            raise ValueError("올바르지 않은 해금 대상 챕터입니다.")

        requirements = (
            self.required_evidence,
            self.required_flags,
            self.required_presentations,
        )

        if any(not isinstance(items, frozenset) for items in requirements):
            raise TypeError("해금 조건은 frozenset이어야 합니다.")

        # 조건이 없는 챕터를 실수로 공개하지 않도록 차단합니다.
        if type(self.requires_completed_prologue) is not bool:
            raise TypeError("Invalid prologue requirement")

        if self.requires_completed_prologue and self.target_chapter != "CH01":
            raise ValueError("Prologue gate is restricted to CH01")

        if not any(requirements) and not self.requires_completed_prologue:
            raise ValueError("최소 하나의 해금 조건이 필요합니다.")

        evidence_pattern = r"E(?:0[1-9]|[12][0-9]|30)"
        presentation_pattern = rf"C(?:0[1-9]|10):{evidence_pattern}"

        if any(
            not isinstance(item, str) or re.fullmatch(evidence_pattern, item) is None
            for item in self.required_evidence
        ):
            raise ValueError("올바르지 않은 필수 증거입니다.")

        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.required_flags
        ):
            raise ValueError("올바르지 않은 필수 플래그입니다.")

        if any(
            not isinstance(item, str)
            or re.fullmatch(presentation_pattern, item) is None
            for item in self.required_presentations
        ):
            raise ValueError("올바르지 않은 증거 제시 조건입니다.")


def next_chapter_choices(
    state: GameState,
) -> tuple[ChapterCode, ...]:
    """Return candidate chapters for the pinned content version."""

    current = state.current_chapter

    if state.content_version == "case001_v7_1":
        index = CHAPTER_ORDER.index(current)
        return CHAPTER_ORDER[index + 1:index + 2]

    unlocked = set(state.unlocked_chapters)

    if current == "CH00":
        return ("CH01",)

    if current == "CH01":
        return tuple(
            chapter
            for chapter in ("CH02", "CH03")
            if chapter not in unlocked
        )

    if current in ("CH02", "CH03"):
        remaining = tuple(
            chapter
            for chapter in ("CH02", "CH03")
            if chapter not in unlocked
        )

        if remaining:
            return remaining

        if "CH04" not in unlocked:
            return ("CH04",)

    return ()



def can_revisit_investigation_chapter(
    state: GameState,
    target_chapter: ChapterCode,
) -> bool:
    """Permit revisits only between unlocked expanded branches."""
    return (
        state.case_id == "CASE-001"
        and state.content_version == "case001_1120"
        and state.phase == GamePhase.INVESTIGATION
        and state.outcome in (None, "ONGOING")
        and state.current_chapter in {"CH02", "CH03"}
        and target_chapter in {"CH02", "CH03"}
        and target_chapter != state.current_chapter
        and {"CH02", "CH03"}.issubset(state.unlocked_chapters)
        and "CH04" not in state.unlocked_chapters
    )


def advance_chapter(
    state: GameState,
    *,
    rule: ChapterUnlockRule | None,
) -> GameState:
    """신뢰된 서버 규칙을 충족하면 다음 챕터 상태를 생성합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    if state.phase != GamePhase.INVESTIGATION:
        raise PermissionError("조사 단계에서만 챕터를 진행할 수 있습니다.")

    if state.outcome not in (None, "ONGOING"):
        raise PermissionError("종료된 게임에서는 챕터를 진행할 수 없습니다.")

    choices = next_chapter_choices(state)

    if not choices:
        raise PermissionError("No next chapter available")

    if not isinstance(rule, ChapterUnlockRule):
        raise PermissionError("Chapter rule required")

    next_chapter = rule.target_chapter

    revisit = can_revisit_investigation_chapter(state, next_chapter)

    if next_chapter not in choices and not revisit:
        raise PermissionError("Chapter transition not allowed")

    if state.content_version == "case001_v7_1":
        current_index = CHAPTER_ORDER.index(
            state.current_chapter
        )

        expected_unlocked = list(
            CHAPTER_ORDER[:current_index + 1]
        )

        if state.unlocked_chapters != expected_unlocked:
            raise ValueError("Invalid legacy chapter history")

    if rule.requires_completed_prologue and (
        state.content_version != "case001_1120"
        or state.current_chapter != "CH00"
    ):
        raise PermissionError("Invalid prologue transition")

    if next_chapter in state.unlocked_chapters and not revisit:
        raise PermissionError("Chapter already unlocked")

    collected = {
        evidence_id
        for evidence_id, evidence in state.evidence.items()
        if evidence.stage in VALID_EVIDENCE_STAGES
    }

    if not rule.required_evidence.issubset(collected):
        raise PermissionError("필수 증거를 획득하지 않았습니다.")

    if not rule.required_flags.issubset(set(state.flags)):
        raise PermissionError("필수 스토리 조건이 충족되지 않았습니다.")

    for presentation in rule.required_presentations:
        npc_id, evidence_id = presentation.split(":", 1)

        if evidence_id not in collected or evidence_id not in state.presented.get(
            npc_id, []
        ):
            raise PermissionError("필수 증거 제시 기록이 없습니다.")

    # 검증된 상태만 생성하고 기존 객체는 변경하지 않습니다.
    return GameState.model_validate(
        {
            **state.model_dump(mode="python"),
            "current_chapter": next_chapter,
            "unlocked_chapters": (
                list(state.unlocked_chapters)
                if revisit
                else [*state.unlocked_chapters, next_chapter]
            ),
            "revision": state.revision + 1,
        }
    )


def advance_chapter_atomic(
    repository: SQLiteCase001Repository,
    session_id: str,
    *,
    rule: ChapterUnlockRule | None,
    expected_revision: int | None = None,
    stage_events: Callable[[GameState], GameState] | None = None,
) -> GameState:
    """챕터 전환과 이벤트 큐를 원자적으로 저장합니다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("게임 상태 저장소가 필요합니다.")

    if expected_revision is not None and (
        type(expected_revision) is not int
        or expected_revision < 0
    ):
        raise ValueError("올바르지 않은 revision입니다.")

    current = repository.load_state(session_id)

    if (
        expected_revision is not None
        and current.revision != expected_revision
    ):
        raise ValueError("GameState revision이 일치하지 않습니다.")

    updated = advance_chapter(current, rule=rule)

    # 새 챕터에서 허용되는 이벤트만 평가합니다.
    if stage_events is not None:
        updated = stage_events(updated)

    return repository.commit_state(
        expected_state=current,
        updated_state=updated,
    )
