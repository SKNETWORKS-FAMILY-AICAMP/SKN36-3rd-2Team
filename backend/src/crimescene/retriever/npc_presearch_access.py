"""CASE-001 NPC별 검색 전 Qdrant 접근 권한 필터."""

from collections.abc import Iterable, Mapping, Sequence
from types import SimpleNamespace
from uuid import UUID

from neo4j import Driver
from qdrant_client import QdrantClient, models

from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.graph_search import CHARACTER_IDS
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.multisource_search import (
    search_multisource_candidates,
)
from crimescene.scenario.npc_access import select_authorized_npc_cards
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"


def _normalize_uuid(value: str) -> str:
    """Qdrant Point UUID를 검증하고 정규화한다."""

    if not isinstance(value, str):
        raise TypeError("Qdrant UUID는 문자열이어야 합니다.")

    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError("유효하지 않은 Qdrant UUID입니다.") from exc


def build_authorized_npc_point_ids(
    *,
    trusted_records: Iterable[HybridChunkRecord],
    npc_cards: Iterable[Mapping[str, object]],
    state: GameState,
    evaluator: PolicyEvaluator,
    active_character_id: str,
    matched_topics: Iterable[str] = (),
) -> frozenset[str]:
    """현재 NPC가 접근할 수 있는 Qdrant UUID를 생성한다.

    접근 정책:
        - 현재 NPC 해금 여부
        - 현재 NPC 소유 지식
        - GameState 접근 조건
        - 증거 수집 조건
        - 증거 제시 조건
        - 질문 주제 조건
        - 진술 supersedes 관계

    서버에서 검증한 원본만 사용한다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("PolicyEvaluator가 필요합니다.")

    if not isinstance(active_character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if active_character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if active_character_id not in state.unlocked_characters:
        return frozenset()

    records = list(trusted_records)
    cards = list(npc_cards)
    topics = tuple(matched_topics)

    # 기존 접근 정책 엔진 재사용
    authorized_cards = select_authorized_npc_cards(
        cards,
        state,
        evaluator,
        active_character_id=active_character_id,
        matched_topics=topics,
    )

    authorized_card_ids = {card.card_id for card in authorized_cards}

    allowed_ids = set()
    seen_ids = set()

    for record in records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("신뢰 청크 타입이 올바르지 않습니다.")

        chunk = record.chunk

        if chunk.case_id != state.case_id:
            raise ValueError("청크 사건 ID가 일치하지 않습니다.")

        point_id = _normalize_uuid(chunk.point_id)

        if point_id in seen_ids:
            raise ValueError("중복된 신뢰 청크 UUID입니다.")

        seen_ids.add(point_id)

        # 플레이어 문서와 다른 NPC 지식은 제외
        if chunk.source_type != "npc_knowledge":
            continue

        if chunk.character_id != active_character_id:
            continue

        # 서버 접근 정책에서 허용한 카드만 검색
        if chunk.source_id not in authorized_card_ids:
            continue

        allowed_ids.add(point_id)

    return frozenset(allowed_ids)


class PolicyScopedQdrantClient:
    """허용된 UUID에 대해서만 검색하도록 제한하는 Qdrant 어댑터.

    기존 Dense/BM25 검색 함수의 query_points 호출에
    HasIdCondition을 강제로 추가한다.

    주의:
        이 어댑터는 NPC 검색 경로 전용이며,
        최종 LLM 접근 권한 검증을 대체하지 않는다.
    """

    def __init__(
        self,
        client: QdrantClient,
        allowed_point_ids: Iterable[str],
    ) -> None:
        if isinstance(allowed_point_ids, (str, bytes)):
            raise TypeError("허용 UUID 목록 형식이 올바르지 않습니다.")

        self._client = client

        self.allowed_point_ids = tuple(
            sorted({_normalize_uuid(value) for value in allowed_point_ids})
        )

    def query_points(self, **kwargs):
        """기존 검색 필터에 서버 승인 UUID 조건을 추가한다."""

        original_filter = kwargs.get("query_filter")

        if not isinstance(original_filter, models.Filter):
            raise TypeError("Qdrant 검색 필터가 필요합니다.")

        # 허용 문서가 없다면 DB에 검색 요청하지 않는다.
        if not self.allowed_point_ids:
            return SimpleNamespace(points=[])

        id_condition = models.HasIdCondition(has_id=list(self.allowed_point_ids))

        # 기존 case_id/source_type/character_id 조건 유지
        secured_filter = original_filter.model_copy(
            update={
                "must": [
                    *(original_filter.must or []),
                    id_condition,
                ]
            }
        )

        secured_kwargs = {
            **kwargs,
            "query_filter": secured_filter,
        }

        return self._client.query_points(**secured_kwargs)


def search_policy_scoped_multisource_candidates(
    query: str,
    *,
    qdrant_client: QdrantClient,
    neo4j_driver: Driver,
    embedder: OllamaEmbedder,
    encoder: KoreanBM25Encoder,
    state: GameState,
    evaluator: PolicyEvaluator,
    active_character_id: str,
    trusted_records: Iterable[HybridChunkRecord],
    npc_cards: Iterable[Mapping[str, object]],
    registry: Sequence[Mapping[str, object]],
    trusted_edges: list[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    allowed_entity_ids: Iterable[str] = (),
    matched_topics: Iterable[str] = (),
    candidate_k: int = 30,
    relation_top_k: int = 20,
    evidence_top_k: int = 10,
    rrf_k: int = 60,
) -> list[FusedSearchCandidate]:
    """NPC별 접근 정책을 검색 전에 적용한 3중 RRF 검색.

    1. GameState 검증
    2. NPC별 검색 가능 UUID 계산
    3. Qdrant HasIdCondition 적용
    4. Dense + BM25 + Graph 검색
    5. 검색 결과 UUID 재확인
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(active_character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if active_character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if active_character_id not in state.unlocked_characters:
        return []

    records = list(trusted_records)
    cards = list(npc_cards)

    topics = tuple(matched_topics)

    # 1. 현재 NPC의 허용 UUID 계산
    approved_ids = build_authorized_npc_point_ids(
        trusted_records=records,
        npc_cards=cards,
        state=state,
        evaluator=evaluator,
        active_character_id=active_character_id,
        matched_topics=topics,
    )

    # 2. 서버 원본의 전체 NPC 지식 UUID
    trusted_ids = {
        _normalize_uuid(record.chunk.point_id)
        for record in records
        if (
            record.chunk.source_type == "npc_knowledge"
            and record.chunk.character_id == active_character_id
        )
    }

    # 3. 접근 정책을 적용한 Qdrant 클라이언트
    scoped_client = PolicyScopedQdrantClient(
        qdrant_client,
        approved_ids,
    )

    # 4. 기존 #19 검색 파이프라인 재사용
    results = search_multisource_candidates(
        query,
        qdrant_client=scoped_client,
        neo4j_driver=neo4j_driver,
        embedder=embedder,
        encoder=encoder,
        state=state,
        active_character_id=active_character_id,
        registry=registry,
        trusted_edges=trusted_edges,
        evidence_rules=evidence_rules,
        trusted_point_ids=trusted_ids,
        allowed_entity_ids=allowed_entity_ids,
        candidate_k=candidate_k,
        relation_top_k=relation_top_k,
        evidence_top_k=evidence_top_k,
        rrf_k=rrf_k,
    )

    # 5. 검색 결과가 정책을 우회하지 않았는지 재확인
    for item in results:
        if item.kind != "chunk":
            continue

        if _normalize_uuid(item.item_id) not in approved_ids:
            raise ValueError("접근 권한이 없는 Qdrant 청크가 검색됐습니다.")

    return results
