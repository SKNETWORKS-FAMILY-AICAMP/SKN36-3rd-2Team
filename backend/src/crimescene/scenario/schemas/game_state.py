from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GamePhase(StrEnum):
    PROLOGUE = "PROLOGUE"
    INVESTIGATION = "INVESTIGATION"
    ACCUSATION = "ACCUSATION"
    FINISHED = "FINISHED"


class EvidenceState(BaseModel):
    """증거별 발견 및 해결 진행 상태."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    stage: str = Field(min_length=1)


class GameState(BaseModel):
    """CASE-001 플레이어의 현재 게임 진행 상태.

    접근 권한 판정에 사용되는 서버 관리 데이터이다.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    # 사건 및 세션
    case_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    # 게임 진행 단계
    # 기본값을 제공해 기존 SQLite 게임 상태와의 호환성을 유지합니다.
    phase: GamePhase = GamePhase.PROLOGUE

    # 해금된 NPC
    unlocked_characters: list[str]

    # 증거별 진행 상태
    # 예: {"E01": {"found": True, "resolved": False}}
    evidence: dict[str, EvidenceState]

    # 게임 진행 플래그
    flags: list[str]

    # 증거 제시 기록
    # 증거 ID -> 제시받은 NPC ID 목록
    presented: dict[str, list[str]]

    # 범인 지목 및 게임 진행
    attempts_left: int = Field(ge=0)
    score: int = Field(ge=0)

    # 게임 결과
    outcome: str | None

    # 심층 엔딩 자격
    deep_eligible: bool

    # 게임 상태 버전
    revision: int = Field(ge=0)

    # 공개된 NPC 지식 카드
    disclosed_cards: list[str]

    # 별도로 열람 권한을 획득한 문서
    document_grants: list[str]
