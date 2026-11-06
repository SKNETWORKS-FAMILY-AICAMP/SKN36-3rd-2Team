from collections.abc import Iterable, Mapping
from uuid import UUID, uuid5

from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.rag_access import (
    AuthorizedRAGChunk,
    build_authorized_rag_context,
)
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState


def build_authorized_hybrid_context(
    records: Iterable[HybridChunkRecord],
    *,
    documents: Iterable[PlayerDocument],
    npc_cards: Iterable[Mapping[str, object]],
    state: GameState,
    evaluator: PolicyEvaluator,
    active_character_id: str | None = None,
    matched_topics: Iterable[str] = (),
    trusted_records: Iterable[HybridChunkRecord] | None = None,
) -> list[AuthorizedRAGChunk]:
    """검색된 Hybrid 청크 중 접근이 허용된 정보만 반환한다.

    반드시 신뢰할 수 있는 전체 NPC 지식 카드 목록을 전달해야 한다.
    검색된 일부 카드만으로 진술 대체 관계를 판단하지 않는다.

    검색 결과의 정책 ID와 본문을 그대로 신뢰하지 않는다.
    """

    all_documents = list(documents)
    all_cards = list(npc_cards)

    # 1. 원본 문서 목록 구성
    document_map: dict[str, PlayerDocument] = {}

    for document in all_documents:
        if document.doc_id in document_map:
            raise ValueError("중복된 원본 문서 ID")

        document_map[document.doc_id] = document

    # 2. 전체 NPC 지식 카드 목록 구성
    card_map: dict[str, Mapping[str, object]] = {}

    for card in all_cards:
        card_id = card.get("id")

        if not isinstance(card_id, str) or not card_id:
            raise ValueError("유효하지 않은 NPC 카드 ID")

        if card_id in card_map:
            raise ValueError("중복된 NPC 카드 ID")

        card_map[card_id] = card

    # 3. 기존 Issue #10 접근 엔진으로 원본 권한 평가
    # NPC 카드는 반드시 전체 목록으로 평가한다.
    authorized_sources = build_authorized_rag_context(
        documents=all_documents,
        npc_cards=all_cards,
        state=state,
        evaluator=evaluator,
        active_character_id=active_character_id,
        matched_topics=matched_topics,
    )

    authorized_map = {
        (source.source_type, source.source_id): source for source in authorized_sources
    }
    # 서버가 관리하는 신뢰 청크 목록
    trusted_by_id: dict[UUID, HybridChunkRecord] = {}

    if trusted_records is not None:
        for trusted in trusted_records:
            if not isinstance(trusted, HybridChunkRecord):
                raise TypeError("신뢰 청크 타입이 올바르지 않습니다.")

            point_id = trusted.chunk.chunk_id

            if point_id in trusted_by_id:
                raise ValueError("중복된 신뢰 청크 UUID")

            trusted_by_id[point_id] = trusted

    results: list[AuthorizedRAGChunk] = []
    seen_chunk_ids: set[UUID] = set()

    # 4. 검색된 청크별 최종 접근 검증
    for record in records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("HybridChunkRecord 타입만 허용합니다.")

        chunk = record.chunk

        source_key = (
            chunk.source_type,
            chunk.source_id,
        )

        # 접근 권한이 없는 원본은 검색 결과에서 제외
        authorized = authorized_map.get(source_key)

        if authorized is None:
            continue

        # 5. 신뢰할 수 있는 원본 데이터 조회
        if chunk.source_type == "player_document":
            original = document_map.get(chunk.source_id)

            if original is None:
                raise ValueError("원본 문서를 찾을 수 없습니다.")

            original_point_id = original.point_id
            original_body = original.body
            original_search_text = original.search_text

            expected_metadata = {
                "case_id": original.case_id,
                "policy_id": original.policy_id,
                "family": original.family,
                "access_scope": original.access_scope,
                "character_id": None,
                "incident_year": original.incident_year,
                "content_hash": original.content_hash,
            }

        else:
            card = card_map.get(chunk.source_id)

            if card is None:
                raise ValueError("원본 NPC 카드를 찾을 수 없습니다.")

            original_point_id = str(card["point_id"])
            original_body = card["body"]
            original_search_text = card["search_text"]

            expected_metadata = {
                "case_id": card["case_id"],
                "policy_id": card["policy_id"],
                "family": card["family"],
                "access_scope": card["access_scope"],
                "character_id": card["character_id"],
                "incident_year": card["incident_year"],
                "content_hash": card["content_hash"],
            }

        # 6. 원본 메타데이터 위조 차단
        for field, expected_value in expected_metadata.items():
            if getattr(chunk, field) != expected_value:
                raise ValueError("청크 원본 메타데이터 불일치")

        # 7. 원본 UUID 및 청크 순서 검증
        parent_uuid = UUID(str(original_point_id))

        if record.parent_point_id != parent_uuid:
            raise ValueError("원본 Point ID 불일치")

        if (
            record.chunk_count < 1
            or record.chunk_index < 0
            or record.chunk_index >= record.chunk_count
        ):
            raise ValueError("청크 순서 정보가 올바르지 않습니다.")

        if record.chunk_index == 0:
            expected_uuid = parent_uuid
        else:
            expected_uuid = uuid5(
                parent_uuid,
                f"rag-chunk:{record.chunk_index}",
            )

        if chunk.chunk_id != expected_uuid:
            raise ValueError("청크 UUID 불일치")

        # 8. 원본 텍스트 검증
        if not isinstance(original_body, str):
            raise TypeError("원본 본문이 올바르지 않습니다.")

        if not isinstance(original_search_text, str):
            raise TypeError("원본 검색 텍스트가 올바르지 않습니다.")

        # 기존 권한 엔진이 승인한 본문과 원본 비교
        if authorized.content != original_body:
            raise ValueError("승인된 원본 본문 불일치")

        if record.chunk_count == 1:
            if chunk.body != original_body or chunk.search_text != original_search_text:
                raise ValueError("원본 청크 내용 불일치")

        else:
            # 신뢰된 청킹 결과가 없으면 접근 거부
            trusted_record = trusted_by_id.get(chunk.chunk_id)

            if trusted_record is None:
                raise ValueError("하위 청크 내용 불일치: 신뢰 청크 없음")

            # UUID뿐 아니라 본문, 정책, 순서 등 전체 비교
            if trusted_record != record:
                raise ValueError("하위 청크 내용 불일치")

            # 원본에 없는 텍스트 유입 차단
            if chunk.body not in original_body or chunk.search_text != chunk.body:
                raise ValueError("하위 청크 내용 불일치")

        # 9. Dense/Sparse 중복 검색 결과 제거
        if chunk.chunk_id in seen_chunk_ids:
            continue

        seen_chunk_ids.add(chunk.chunk_id)

        # 10. LLM 전달용 안전한 모델로 변환
        results.append(
            AuthorizedRAGChunk(
                source_id=chunk.source_id,
                source_type=chunk.source_type,
                content=chunk.body,
                truth_status=authorized.truth_status,
                character_id=authorized.character_id,
            )
        )

    return results
