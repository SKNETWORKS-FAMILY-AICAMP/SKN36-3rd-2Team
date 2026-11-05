from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crimescene.scenario.models import SourceReference


class KnowledgeType(StrEnum):
    """NPC가 보유한 정보의 유형."""

    OBSERVATION = "OBSERVATION"
    MEMORY = "MEMORY"
    HEARSAY = "HEARSAY"
    CLAIM = "CLAIM"


class DisclosureCondition(StrEnum):
    """NPC 정보 공개 조건."""

    OPEN = "OPEN"
    QUESTION = "QUESTION"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    EVIDENCE_PRESENTED = "EVIDENCE_PRESENTED"
    FLAG_UNLOCKED = "FLAG_UNLOCKED"


class DisclosureRule(BaseModel):
    """NPC 지식 공개 조건 정의."""

    model_config = ConfigDict(extra="forbid")

    condition: DisclosureCondition

    reference_id: str | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> Self:
        """공개 조건과 참조 ID의 조합을 검증."""

        if self.condition == DisclosureCondition.OPEN:
            if self.reference_id is not None:
                raise ValueError("OPEN 조건에는 reference_id를 지정할 수 없습니다.")

        else:
            if not self.reference_id or not self.reference_id.strip():
                raise ValueError("조건부 공개에는 reference_id가 필요합니다.")

        return self


class NPCKnowledgeCard(BaseModel):
    """NPC별 지식 카드."""

    model_config = ConfigDict(extra="forbid")

    knowledge_id: str = Field(min_length=1)

    npc_id: str = Field(min_length=1)

    knowledge_type: KnowledgeType

    content: str = Field(min_length=1)

    disclosure_rule: DisclosureRule

    source_refs: list[SourceReference] = Field(default_factory=list)

    access_scope: Literal["NPC_ONLY"] = "NPC_ONLY"
