from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


class GamePhase(StrEnum):
    PROLOGUE = "PROLOGUE"
    INVESTIGATION = "INVESTIGATION"
    ACCUSATION = "ACCUSATION"
    FINISHED = "FINISHED"


# CASE-001에서 지원하는 챕터 코드
ChapterCode = Literal["CH00", "CH01", "CH02", "CH03", "CH04"]


class EvidenceState(BaseModel):
    """증거별 발견 및 해결 진행 상태."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    stage: str = Field(min_length=1)


class GameState(BaseModel):
    """CASE-001 플레이어의 현재 게임 진행 상태.

    접근 권한 판정에 사용되는 서버 관리 데이터입니다.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    # ============================================================
    # 1. 사건 및 세션
    # ============================================================

    case_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    # ============================================================
    # 2. 게임 진행 상태
    # ============================================================

    # 기존 SQLite 데이터와의 호환성을 위해 기본값 유지
    phase: GamePhase = GamePhase.PROLOGUE

    # 현재 진행 중인 챕터
    current_chapter: ChapterCode = "CH00"

    # 플레이어가 해금한 챕터
    unlocked_chapters: list[ChapterCode] = Field(
        default_factory=lambda: ["CH00"],
        min_length=1,
        max_length=5,
    )

    # ============================================================
    # 3. NPC 및 증거 진행 상태
    # ============================================================

    # 해금된 NPC
    unlocked_characters: list[str]

    # 증거별 진행 상태
    # 예: {"E01": {"stage": "found"}}
    evidence: dict[str, EvidenceState]

    # 게임 진행 플래그
    flags: list[str]

    # Server-owned event queue. Defaults preserve legacy SQLite saves.
    queued_story_events: list[str] = Field(
        default_factory=list,
        max_length=30,
    )

    # Events acknowledged after successful client-side display.
    acknowledged_story_events: list[str] = Field(
        default_factory=list,
        max_length=30,
    )

    @field_validator("acknowledged_story_events")
    @classmethod
    def validate_acknowledged_story_events(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate acknowledged event ID")

        queued = info.data.get("queued_story_events", [])

        if not set(values).issubset(set(queued)):
            raise ValueError("Cannot acknowledge an unqueued event")

        return values

    @field_validator("queued_story_events")
    @classmethod
    def validate_queued_story_events(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate story event ID")

        for value in values:
            if (
                len(value) != 9
                or not value.startswith("STORY_")
                or not all("0" <= digit <= "9" for digit in value[6:])
            ):
                raise ValueError("Invalid story event ID")

        return values

    # 증거 제시 기록
    # NPC ID -> 제시한 증거 ID 목록
    presented: dict[str, list[str]]

    # ============================================================
    # 4. 범인 지목 및 게임 결과
    # ============================================================

    attempts_left: int = Field(ge=0)
    score: int = Field(ge=0)

    outcome: str | None
    deep_eligible: bool

    # 게임 상태 버전
    revision: int = Field(ge=0)

    # ============================================================
    # 5. 플레이어 콘텐츠 공개 상태
    # ============================================================

    # 공개된 NPC 지식 카드
    disclosed_cards: list[str]

    # 별도로 열람 권한을 획득한 문서
    document_grants: list[str]

    # ============================================================
    # 6. 챕터 진행 상태 검증
    # ============================================================

    @model_validator(mode="after")
    def validate_chapter_progress(self):
        """챕터 진행 상태의 무결성을 검증합니다."""

        chapters = self.unlocked_chapters

        # 동일 챕터 중복 해금 방지
        if len(chapters) != len(set(chapters)):
            raise ValueError("중복된 해금 챕터가 존재합니다.")

        # 시작 챕터는 항상 포함
        if "CH00" not in chapters:
            raise ValueError("시작 챕터 CH00은 반드시 포함해야 합니다.")

        # 해금되지 않은 챕터로 이동 방지
        if self.current_chapter not in chapters:
            raise ValueError("해금되지 않은 챕터로 이동할 수 없습니다.")

        # 프롤로그 진행 중에는 CH00만 허용
        if self.phase == GamePhase.PROLOGUE and self.current_chapter != "CH00":
            raise ValueError("프롤로그에서는 CH00만 진행할 수 있습니다.")

        return self
