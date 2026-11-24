"""CASE-001 서버 측 챕터 해금 및 전환 엔진."""

import re
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
        if not any(requirements):
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

    current_index = CHAPTER_ORDER.index(state.current_chapter)

    if current_index == len(CHAPTER_ORDER) - 1:
        raise PermissionError("마지막 챕터입니다.")

    next_chapter = CHAPTER_ORDER[current_index + 1]

    # 서버가 검증한 규칙이 없으면 공개하지 않습니다.
    if not isinstance(rule, ChapterUnlockRule):
        raise PermissionError("챕터 해금 규칙이 등록되지 않았습니다.")

    if rule.target_chapter != next_chapter:
        raise PermissionError("다음 챕터만 해금할 수 있습니다.")

    # 기존 해금 기록이 연속된 진행 경로인지 확인합니다.
    expected_unlocked = list(CHAPTER_ORDER[: current_index + 1])

    if state.unlocked_chapters != expected_unlocked:
        raise ValueError("챕터 진행 기록이 일치하지 않습니다.")

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
            "unlocked_chapters": [
                *state.unlocked_chapters,
                next_chapter,
            ],
            "revision": state.revision + 1,
        }
    )


def advance_chapter_atomic(
    repository: SQLiteCase001Repository,
    session_id: str,
    *,
    rule: ChapterUnlockRule | None,
    expected_revision: int | None = None,
) -> GameState:
    """최신 서버 상태를 검사한 후 SQLite에 원자적으로 저장합니다."""

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

    # GameState와 NPC 세션 revision을 원자적으로 갱신합니다.
    return repository.commit_state(
        expected_state=current,
        updated_state=updated,
    )
