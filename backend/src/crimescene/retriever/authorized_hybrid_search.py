"""GameState 접근 제어를 적용한 Hybrid RAG 검색."""

from collections.abc import Iterable, Mapping

from qdrant_client import QdrantClient

from crimescene.ingest.hybrid_access import (
    build_authorized_hybrid_context,
)
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.hybrid_search import (
    search_hybrid_candidates,
)
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.rag_access import AuthorizedRAGChunk
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState

DEFAULT_CANDIDATE_K = 100
DEFAULT_TOP_K = 10


def search_authorized_hybrid_context(
    query: str,
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    encoder: KoreanBM25Encoder,
    trusted_records: Iterable[HybridChunkRecord],
    documents: Iterable[PlayerDocument],
    npc_cards: Iterable[Mapping[str, object]],
    state: GameState,
    evaluator: PolicyEvaluator,
    active_character_id: str | None = None,
    matched_topics: Iterable[str] = (),
    candidate_k: int = DEFAULT_CANDIDATE_K,
    top_k: int = DEFAULT_TOP_K,
) -> list[AuthorizedRAGChunk]:
    """검색 결과 중 현재 게임 상태에서 허용된 정보만 반환한다.

    신뢰 원본:
        trusted_records, documents, npc_cards

    비신뢰 데이터:
        Qdrant 검색 결과

    주의:
        신뢰 원본은 반드시 서버에서 로딩한 데이터여야 한다.
        Qdrant Payload를 신뢰 원본으로 사용하지 않는다.
    """

    # 1. 게임 상태 검증
    if not isinstance(state, GameState):
        raise TypeError("GameState 타입이 필요합니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("PolicyEvaluator 타입이 필요합니다.")

    # 2. 검색 개수 검증
    if (
        isinstance(candidate_k, bool)
        or not isinstance(candidate_k, int)
        or not 1 <= candidate_k <= 100
    ):
        raise ValueError("candidate_k는 1~100 사이의 정수여야 합니다.")

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or not 1 <= top_k <= candidate_k
    ):
        raise ValueError("top_k는 1 이상 candidate_k 이하여야 합니다.")

    # 3. 서버가 관리하는 신뢰 원본 확보
    records = list(trusted_records)
    all_documents = list(documents)
    all_cards = list(npc_cards)

    if not records:
        raise ValueError("신뢰할 수 있는 RAG 청크가 없습니다.")

    # 4. 신뢰 청크 UUID 색인
    record_by_id: dict[str, HybridChunkRecord] = {}

    for record in records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("신뢰 청크 타입이 올바르지 않습니다.")

        if record.chunk.case_id != state.case_id:
            raise ValueError("게임 상태와 청크의 사건 ID가 일치하지 않습니다.")

        point_id = record.chunk.point_id

        if point_id in record_by_id:
            raise ValueError("중복된 신뢰 청크 UUID가 존재합니다.")

        record_by_id[point_id] = record

    # 5. 검색 모드 자동 결정
    if active_character_id is None:
        source_type = "player_document"
    else:
        source_type = "npc_knowledge"

    # 6. Dense + BM25 + RRF 검색
    # 최종 Top-K는 권한 검증 이후 적용한다.
    candidates = search_hybrid_candidates(
        query,
        client=client,
        embedder=embedder,
        encoder=encoder,
        source_type=source_type,
        case_id=state.case_id,
        character_id=active_character_id,
        candidate_k=candidate_k,
        top_k=candidate_k,
    )

    # 7. 검색 UUID를 신뢰 원본 청크와 연결
    selected_records = []

    for candidate in candidates:
        record = record_by_id.get(candidate.point_id)

        if record is None:
            # Qdrant에는 있지만 서버 원본에는 없는 청크
            # 정보 누출 방지를 위해 실패 처리
            raise ValueError("신뢰할 수 없는 검색 후보 UUID가 존재합니다.")

        selected_records.append(record)

    if not selected_records:
        return []

    # 8. 기존 Issue #10, #12 접근 정책 엔진 재사용
    # 전체 NPC 카드 목록을 전달하여 supersedes 검증
    authorized = build_authorized_hybrid_context(
        selected_records,
        documents=all_documents,
        npc_cards=all_cards,
        state=state,
        evaluator=evaluator,
        active_character_id=active_character_id,
        matched_topics=tuple(matched_topics),
        trusted_records=records,
    )

    # 9. 권한 검증을 마친 후 최종 결과 개수 제한
    return authorized[:top_k]
