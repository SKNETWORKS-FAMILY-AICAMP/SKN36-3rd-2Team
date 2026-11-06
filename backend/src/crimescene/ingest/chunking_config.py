from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChunkingMode(StrEnum):
    """RAG 문서 청킹 전략."""

    WHOLE = "whole"
    FIXED = "fixed"
    SEMANTIC_FIXED = "semantic_fixed"


class ChunkingConfig(BaseModel):
    """CASE-001 RAG 청킹 설정."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    mode: ChunkingMode = ChunkingMode.SEMANTIC_FIXED

    # 청크 크기 (문자 수 기준)
    min_chunk_chars: int = Field(
        default=120,
        ge=1,
    )

    max_chunk_chars: int = Field(
        default=800,
        ge=2,
    )

    # 청크 간 중복 문자 수
    overlap_chars: int = Field(
        default=80,
        ge=0,
    )

    # 의미 기반 청킹의 초기 유사도 기준
    semantic_similarity_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> Self:
        """청크 크기 및 중복 범위 검증."""

        if self.min_chunk_chars > self.max_chunk_chars:
            raise ValueError("최소 청크 크기는 최대 크기보다 클 수 없습니다.")

        if self.overlap_chars >= self.max_chunk_chars:
            raise ValueError("Overlap은 최대 청크 크기보다 작아야 합니다.")

        return self
