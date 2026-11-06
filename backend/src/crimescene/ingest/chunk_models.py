from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crimescene.scenario.schemas.access_policy import PolicyId


class RAGChunk(BaseModel):
    """CASE-001 RAG 검색용 내부 청크 데이터 모델.

    이 모델은 접근 권한 승인을 의미하지 않는다.
    검색 결과를 LLM에 전달하기 전에 반드시
    기존 RAG 접근 정책 엔진을 통과해야 한다.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    # 기존 원본 point_id를 재사용한다.
    chunk_id: UUID

    # 원본 데이터 추적
    source_id: str = Field(min_length=1)

    source_type: Literal[
        "player_document",
        "npc_knowledge",
    ]

    case_id: str = Field(min_length=1)

    # 접근 정책 연결
    policy_id: PolicyId

    # 문서 분류
    family: str = Field(min_length=1)

    access_scope: Literal[
        "collected_evidence",
        "conditional_record",
        "character_only",
    ]

    # NPC 정보
    character_id: str | None = None

    # 사건 발생 연도
    incident_year: int | None = None

    # 원본 무결성
    content_hash: str = Field(min_length=1)

    # 검색 및 원본 텍스트
    search_text: str = Field(
        min_length=1,
        repr=False,
    )

    body: str = Field(
        min_length=1,
        repr=False,
    )

    @property
    def point_id(self) -> str:
        """Qdrant Point ID로 사용할 UUID 문자열."""
        return str(self.chunk_id)

    @model_validator(mode="after")
    def validate_source_access(self) -> Self:
        """원본 유형에 맞는 접근 범위인지 검사한다."""

        if self.source_type == "npc_knowledge":
            if self.access_scope != "character_only":
                raise ValueError("NPC 지식은 character_only 범위여야 합니다.")

            if not self.character_id:
                raise ValueError("NPC 지식에는 character_id가 필요합니다.")

        elif self.source_type == "player_document":
            if self.access_scope == "character_only":
                raise ValueError("플레이어 문서에 NPC 전용 범위를 사용할 수 없습니다.")

            if self.character_id is not None:
                raise ValueError("플레이어 문서에 character_id를 지정할 수 없습니다.")

        return self
