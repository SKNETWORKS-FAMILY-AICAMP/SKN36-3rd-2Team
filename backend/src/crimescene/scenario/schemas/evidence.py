from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
)

EvidenceId = Annotated[
    str,
    StringConstraints(pattern=r"^E\d{2}$"),
]


class EvidenceRule(BaseModel):
    """개별 증거의 수집 및 활용 규칙."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    # 증거 기본 정보
    name: str = Field(min_length=1)
    score: int = Field(ge=0)
    holder: str

    # 증거 획득 및 활용 조건
    prerequisites: list[str]
    presentation: list[str]

    # 증거 관련 질문 또는 규칙
    q: list[str]


class EvidenceCatalog(RootModel[dict[EvidenceId, EvidenceRule]]):
    """CASE-001 증거 규칙 목록."""
