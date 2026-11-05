from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.models import SourceReference


class CaseTruth(BaseModel):
    """게임 엔진 전용 사건 진실 원장.

    범인, 동기, 사망 원인 등 실제 사건의 진실을 관리한다.

    주의:
    - NPC 프롬프트에 직접 전달하지 않는다.
    - 일반 RAG 검색 대상으로 적재하지 않는다.
    - 범인 지목 및 게임 결과 판정에 사용한다.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)

    # 실제 범인
    perpetrator_character_id: str = Field(min_length=1)

    # 범행 동기
    motive: str = Field(min_length=1)

    # 사망 원인
    cause_of_death: str = Field(min_length=1)

    # 범행 방법
    crime_method: str = Field(min_length=1)

    # 실제 범행이 발생한 이벤트 ID
    crime_event_id: str = Field(min_length=1)

    # 관련 사건
    related_event_ids: list[str] = Field(default_factory=list)

    # 관련 장소
    related_location_ids: list[str] = Field(default_factory=list)

    # 관련 증거
    related_evidence_ids: list[str] = Field(default_factory=list)

    # 데이터 출처
    source_refs: list[SourceReference] = Field(default_factory=list)

    # 게임 엔진 전용 데이터
    access_scope: Literal["ENGINE_ONLY"] = "ENGINE_ONLY"
