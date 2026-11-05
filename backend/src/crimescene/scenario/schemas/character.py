from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CharacterCardEffects(BaseModel):
    """NPC 지식 카드 공개 후 발생 가능한 게임 상태 효과."""

    model_config = ConfigDict(extra="forbid")

    find: list[str]
    flags: list[str]


class CharacterKnowledgeCard(BaseModel):
    """v7.1 원본 캐릭터에 포함된 지식 카드."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    body: str = Field(min_length=1)

    stance: Literal["fact", "character_claim"]

    claim_group: str = Field(min_length=1)
    stage_priority: int = Field(ge=0)

    supersedes: list[str]
    effects: CharacterCardEffects


class CharacterProfile(BaseModel):
    """v7.1 NPC 관리자 전용 원본 프로필.

    주의:
    - 비공개 사건 정보와 인물별 비밀을 포함한다.
    - NPC 프롬프트에 직접 전달하지 않는다.
    - 공개 RAG 검색 인덱스에 적재하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    # 기본 정보
    id: str = Field(pattern=r"^C(0[1-9]|10)$")
    name: str = Field(min_length=1)

    # 인물의 성격 및 외형
    voice: str = Field(min_length=1)
    appearance: str = Field(min_length=1)

    # 최초 진술 및 알리바이
    initial: str = Field(min_length=1)
    alibi: str = Field(min_length=1)

    # 관리자 전용 비밀
    secret_2026: str = Field(min_length=1)
    secret_2016: str = Field(min_length=1)

    # 인물의 서사 변화
    trajectory: str = Field(min_length=1)

    # 예상 질문
    questions: list[str] = Field(min_length=1)

    # NPC 지식 카드
    cards: list[CharacterKnowledgeCard] = Field(min_length=1)
