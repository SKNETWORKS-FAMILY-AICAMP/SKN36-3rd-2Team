from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.models import SourceReference


class StatementTruthStatus(StrEnum):
    """NPC 진술의 객관적 사실 일치 여부."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    PARTIALLY_TRUE = "PARTIALLY_TRUE"
    UNVERIFIED = "UNVERIFIED"


class StatementIntent(StrEnum):
    """NPC가 해당 진술을 한 의도."""

    HONEST = "HONEST"
    DECEPTIVE = "DECEPTIVE"
    MISTAKEN = "MISTAKEN"
    UNKNOWN = "UNKNOWN"


class StatementAssessment(BaseModel):
    """게임 엔진 전용 NPC 진술 평가 데이터.

    NPC가 알고 있다고 설정된 내용과 실제 사건의
    진실을 비교하기 위한 모델이다.

    NPC의 일반적인 RAG 검색 대상으로 사용하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    assessment_id: str = Field(min_length=1)

    case_id: str = Field(min_length=1)

    npc_id: str = Field(min_length=1)

    knowledge_id: str = Field(min_length=1)

    truth_status: StatementTruthStatus

    statement_intent: StatementIntent = StatementIntent.UNKNOWN

    related_event_ids: list[str] = Field(default_factory=list)

    explanation: str | None = None

    source_refs: list[SourceReference] = Field(default_factory=list)

    access_scope: Literal["ENGINE_ONLY"] = "ENGINE_ONLY"
