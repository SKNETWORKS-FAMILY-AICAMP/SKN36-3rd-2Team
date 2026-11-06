from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.document_access import (
    select_authorized_player_documents,
)
from crimescene.scenario.npc_access import (
    select_authorized_npc_cards,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState


class AuthorizedRAGChunk(BaseModel):
    """LLM에 전달할 수 있도록 접근 검사를 마친 정보."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_id: str = Field(min_length=1)

    source_type: Literal[
        "player_document",
        "npc_knowledge",
    ]

    content: str = Field(min_length=1)

    truth_status: str | None = None

    character_id: str | None = None


def build_authorized_rag_context(
    documents: Iterable[PlayerDocument],
    npc_cards: Iterable[Mapping[str, object]],
    state: GameState,
    evaluator: PolicyEvaluator,
    *,
    active_character_id: str | None = None,
    matched_topics: Iterable[str] = (),
) -> list[AuthorizedRAGChunk]:
    """현재 게임 상태에서 공개 가능한 RAG 정보만 구성한다.

    documents와 npc_cards는 검색 후보 데이터이다.
    실제 LLM 호출 이전에 반드시 이 함수를 통과시켜야 한다.
    """

    topics = tuple(matched_topics)
    chunks: list[AuthorizedRAGChunk] = []

    # 1. 플레이어 조사 모드
    # NPC가 지정되지 않은 경우에만 플레이어 문서를 전달한다.
    if active_character_id is None:
        allowed_documents = select_authorized_player_documents(
            documents,
            state,
            evaluator,
            matched_topics=topics,
        )

        for document in allowed_documents:
            chunks.append(
                AuthorizedRAGChunk(
                    source_id=document.doc_id,
                    source_type="player_document",
                    content=document.content,
                )
            )

        return chunks

    # 2. NPC 대화 모드
    # 플레이어 문서는 NPC 지식으로 자동 승격하지 않는다.
    # 아래의 NPC 지식 접근 검사 로직으로 계속 진행한다.

    # 3. NPC별 지식 접근 검사
    allowed_cards = select_authorized_npc_cards(
        npc_cards,
        state,
        evaluator,
        active_character_id=active_character_id,
        matched_topics=topics,
    )

    for card in allowed_cards:
        chunks.append(
            AuthorizedRAGChunk(
                source_id=card.card_id,
                source_type="npc_knowledge",
                content=card.content,
                truth_status=card.truth_status,
                character_id=card.character_id,
            )
        )

    return chunks
