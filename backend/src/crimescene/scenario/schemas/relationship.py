from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationshipSourceEdge(BaseModel):
    """v7.1 원본 인물·사건 관계 데이터.

    관계의 진위와 공개 조건을 구분한다.
    """

    model_config = ConfigDict(extra="forbid")

    # 사건 및 관계 식별 정보
    case_id: str = Field(min_length=1)
    edge_id: str = Field(pattern=r"^REL-\d{3}$")

    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation: str = Field(min_length=1)

    # 관계 발생 시점
    incident_year: int

    valid_from: date
    valid_to: date

    temporal_precision: Literal[
        "second",
        "minute",
        "day",
        "part_of_day",
        "month",
        "year",
    ]

    # 관계의 사실 여부
    truth_status: Literal[
        "documented",
        "witness_statement",
        "hypothesis",
        "uncorroborated_claim",
    ]

    # 원본 문서 및 관계 주장 인물
    source_doc_ids: list[str]
    asserted_by: list[str]

    # 공개 범위
    access_scope: Literal[
        "public",
        "conditional",
        "ending_only",
    ]

    # 관계 공개 조건
    required_evidence: list[str]
    required_presentations: list[str]
    required_flags: list[str]
    required_ending: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """관계 종료일이 시작일보다 빠르지 않은지 확인."""

        if self.valid_to < self.valid_from:
            raise ValueError("관계 종료일은 시작일보다 빠를 수 없습니다.")

        return self


class HiddenRelationshipEdge(BaseModel):
    """관리자 전용 비밀 관계.

    NPC 프롬프트 및 공개 RAG 검색에 직접 전달하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target_id: str = Field(min_length=1)

    year: int

    access_scope: Literal["admin_only"]
