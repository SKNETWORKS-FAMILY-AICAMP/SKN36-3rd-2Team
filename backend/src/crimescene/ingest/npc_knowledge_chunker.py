from collections.abc import Collection, Iterable, Mapping

from pydantic import Field

from crimescene.ingest.chunk_models import RAGChunk
from crimescene.scenario.npc_access import NPCKnowledgeCardV71


class _NPCChunkInput(NPCKnowledgeCardV71):
    """청킹에 필요한 CASE-001 v7.1 NPC 데이터 필드.

    기존 NPC 접근 검증 모델을 재사용한다.
    원본의 나머지 메타데이터는 청크로 전달하지 않는다.
    """

    point_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    incident_year: int | None
    content_hash: str = Field(min_length=1)
    search_text: str = Field(min_length=1)


def build_npc_knowledge_chunks(
    cards: Iterable[Mapping[str, object]],
    *,
    expected_case_id: str,
    valid_policy_ids: Collection[str],
) -> list[RAGChunk]:
    """NPC 지식 카드를 RAG 청크로 변환한다.

    카드 1개를 청크 1개로 유지한다.

    정책 참조 또는 데이터 검증에 실패하면
    전체 청킹 작업을 중단한다.

    이 함수는 NPC 지식의 공개를 승인하지 않는다.
    실제 검색 및 LLM 전달 시 접근 정책을 재검증해야 한다.
    """

    # 1. 사건 ID 검증
    if not expected_case_id or not expected_case_id.strip():
        raise ValueError("유효한 사건 ID가 필요합니다.")

    # 2. 접근 정책 목록 확인
    if not valid_policy_ids:
        raise ValueError("접근 정책 목록이 비어 있습니다.")

    chunks: list[RAGChunk] = []

    seen_card_ids: set[str] = set()
    seen_point_ids: set[str] = set()

    for raw_card in cards:
        # 3. 입력 타입 확인
        if not isinstance(raw_card, Mapping):
            raise TypeError("NPC 지식 카드는 Mapping 타입이어야 합니다.")

        # 4. 기존 NPC 접근 스키마 및 청킹 필드 검증
        card = _NPCChunkInput.model_validate(raw_card)

        # 5. 사건 ID 일치 확인
        if card.case_id != expected_case_id:
            raise ValueError(f"사건 ID 불일치: {card.id}")

        # 6. 접근 정책 존재 확인
        if card.policy_id not in valid_policy_ids:
            raise ValueError(f"등록되지 않은 접근 정책: {card.policy_id}")

        # 7. NPC 식별자 확인
        if not card.character_id.strip():
            raise ValueError(f"NPC 식별자 누락: {card.id}")

        # 8. 카드의 캐릭터 조건 일치 확인
        if (
            card.required_character is not None
            and card.required_character != card.character_id
        ):
            raise ValueError(f"NPC 캐릭터 조건 불일치: {card.id}")

        # 9. 카드 ID 중복 확인
        if card.id in seen_card_ids:
            raise ValueError(f"중복 NPC 카드 ID: {card.id}")

        # 10. 허용된 메타데이터만 청크에 전달
        chunk = RAGChunk(
            chunk_id=card.point_id,
            source_id=card.id,
            source_type="npc_knowledge",
            case_id=card.case_id,
            policy_id=card.policy_id,
            family=card.family,
            access_scope=card.access_scope,
            character_id=card.character_id,
            incident_year=card.incident_year,
            content_hash=card.content_hash,
            search_text=card.search_text,
            body=card.body,
        )

        # 11. Point ID 중복 확인
        if chunk.point_id in seen_point_ids:
            raise ValueError(f"중복 Point ID: {chunk.point_id}")

        seen_card_ids.add(card.id)
        seen_point_ids.add(chunk.point_id)

        chunks.append(chunk)

    # 12. 빈 데이터 차단
    if not chunks:
        raise ValueError("청킹 대상 NPC 지식 카드가 없습니다.")

    return chunks
