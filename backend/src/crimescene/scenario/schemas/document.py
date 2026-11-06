from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlayerDocument(BaseModel):
    """CASE-001 플레이어용 문서 데이터 모델."""

    model_config = ConfigDict(extra="forbid")

    # 문서 기본 정보
    doc_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)

    # 문서 분류
    family: Literal[
        "evidence",
        "world",
        "supplementary",
    ]

    # 문서 공개 범위
    access_scope: Literal[
        "collected_evidence",
        "conditional_record",
    ]

    # 게임 내 기록 상태
    truth_status: Literal["documented_in_game"]

    # 증거 및 인물 참조
    source_evidence_ids: list[str]
    known_by_character_ids: list[str]
    source_doc_ids: list[str]

    # 공개 조건
    required_evidence: list[str]
    required_presentations: list[str]
    required_flags: list[str]
    required_ending: str | None

    # 보호해야 하는 사실
    protected_fact_ids: list[str]

    # 사건 발생 시점
    incident_year: int | None
    incident_years: list[int]

    # 출처 및 추적 정보
    source_refs: list[str | dict[str, Any]]
    record_id: str = Field(min_length=1)
    point_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)

    # 데이터 버전 관리
    state_version: str
    content_version: str
    build_id: str
    content_hash: str

    # RAG 검색용 텍스트
    search_text: str
