from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    RootModel,
    StringConstraints,
)

PolicyId = Annotated[
    str,
    StringConstraints(pattern=r"^POL-.+$"),
]


class AccessPolicy(BaseModel):
    """CASE-001 v7.1 문서 및 NPC 지식 접근 정책."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    # 필요한 증거
    required_evidence: list[str]

    # NPC에게 특정 증거를 제시한 기록
    # 예: C03:E05
    required_presentations: list[str]

    # 게임 진행 플래그
    required_flags: list[str]

    # 특정 엔딩에 도달해야 하는 경우
    required_ending: str | None

    # 질문 또는 대화 주제
    required_topics: list[str]

    # 이전에 공개된 NPC 지식 카드
    required_disclosed_cards: list[str]

    # 정책이 적용되는 NPC
    # 정책이 적용되는 NPC
    # NPC와 무관한 정책은 필드가 생략될 수 있음
    required_character: str | None = None


class AccessPolicyCatalog(RootModel[dict[PolicyId, AccessPolicy]]):
    """정책 ID를 Key로 사용하는 접근 정책 목록."""
