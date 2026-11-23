
"""Multi-Agent 공통 실행 계약.

Python 3.13 / Pydantic 2.14
"""

from enum import StrEnum
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
    GameState,
)


class AgentType(StrEnum):
    NPC = "npc"
    DEDUCTION = "deduction"
    HINT = "hint"


class AgentRequest(BaseModel):
    """플레이어가 요청할 수 있는 정보만 포함합니다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_type: AgentType
    message: str = Field(min_length=1, max_length=200)
    presented_evidence_id: str | None = Field(
        default=None,
        pattern=r"^E(?:0[1-9]|10)$",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("메시지가 비어 있습니다.")
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if (
            self.agent_type != AgentType.NPC
            and self.presented_evidence_id is not None
        ):
            raise ValueError(
                "증거 제시는 NPC Agent에서만 허용됩니다."
            )
        return self


class AgentContext(BaseModel):
    """서버가 생성하는 읽기 전용 게임 상태 스냅샷."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    session_id: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1)
    revision: int = Field(ge=0)

    phase: GamePhase
    current_chapter: ChapterCode

    unlocked_characters: tuple[str, ...]
    collected_evidence_ids: tuple[str, ...]
    active_character_id: str | None = None

    @model_validator(mode="after")
    def validate_active_character(self) -> Self:
        if (
            self.active_character_id is not None
            and self.active_character_id
            not in self.unlocked_characters
        ):
            raise ValueError("해금되지 않은 NPC입니다.")
        return self

    @classmethod
    def from_game_state(
        cls,
        state: GameState,
        *,
        active_character_id: str | None = None,
    ) -> Self:
        """소유권 검증을 마친 서버 GameState만 전달해야 합니다."""
        if not isinstance(state, GameState):
            raise TypeError("GameState가 필요합니다.")

        return cls(
            session_id=state.session_id,
            case_id=state.case_id,
            revision=state.revision,
            phase=state.phase,
            current_chapter=state.current_chapter,
            unlocked_characters=tuple(
                sorted(state.unlocked_characters)
            ),
            collected_evidence_ids=tuple(
                sorted(state.evidence)
            ),
            active_character_id=active_character_id,
        )


class AgentResult(BaseModel):
    """Agent의 내부 실행 결과. 외부 반환 전 추가 검증이 필요합니다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_type: AgentType
    text: str = Field(min_length=1)
    source_ids: tuple[str, ...] = ()


class AgentExecutor(Protocol):
    """모든 Agent가 따라야 하는 실행 인터페이스."""

    @property
    def agent_type(self) -> AgentType:
        """Agent 식별자."""
        ...

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> AgentResult:
        """검증된 요청과 서버 컨텍스트를 사용해 실행합니다."""
        ...
