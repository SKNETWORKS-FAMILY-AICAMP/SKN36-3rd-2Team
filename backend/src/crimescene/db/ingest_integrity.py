"""CASE-001 Qdrant / Neo4j 적재 전 무결성 검증."""

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from crimescene.db.neo4j_event_ingest import build_admin_graph_rows
from crimescene.db.neo4j_ingest import validate_graph_data
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge
from crimescene.scenario.source_timeline import SourceTimelineEvent

CASE_ID = "CASE-001"

EVIDENCE_ID_PATTERN = re.compile(r"^E\d{2}$")

ALLOWED_HOLDER_TYPES = frozenset({"Person", "Place", "Object", "Organization"})


@dataclass(frozen=True)
class VectorIntegrityReport:
    """Qdrant 적재 전 검증 결과."""

    point_count: int
    source_count: int


@dataclass(frozen=True)
class GraphIntegrityReport:
    """Neo4j 적재 전 검증 결과."""

    entity_count: int
    relationship_count: int
    evidence_count: int
    event_count: int
    mention_count: int


def validate_qdrant_records(
    records: Iterable[HybridChunkRecord],
    *,
    document_ids: Collection[str],
    npc_card_ids: Collection[str],
    valid_policy_ids: Collection[str],
    case_id: str = CASE_ID,
) -> VectorIntegrityReport:
    """Qdrant에 적재할 청크의 ID와 참조 무결성을 검사한다."""

    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("사건 ID가 비어 있습니다.")

    source_records = list(records)

    if not source_records:
        raise ValueError("Qdrant 검증 대상이 비어 있습니다.")

    document_ids = set(document_ids)
    npc_card_ids = set(npc_card_ids)
    policy_ids = set(valid_policy_ids)

    if not policy_ids:
        raise ValueError("접근 정책 목록이 비어 있습니다.")

    seen_points: set[UUID] = set()

    # (source_type, source_id) -> 청크 목록
    sources: dict[
        tuple[str, str],
        list[HybridChunkRecord],
    ] = defaultdict(list)

    # 원본 UUID가 서로 다른 source에 재사용되는 것도 차단
    parent_owners: dict[UUID, tuple[str, str]] = {}

    for record in source_records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("HybridChunkRecord 타입이 필요합니다.")

        chunk = record.chunk

        if chunk.case_id != case_id:
            raise ValueError(f"청크 사건 ID 불일치: {chunk.source_id}")

        if chunk.chunk_id in seen_points:
            raise ValueError(f"중복 Qdrant Point UUID: {chunk.chunk_id}")

        seen_points.add(chunk.chunk_id)

        if chunk.policy_id not in policy_ids:
            raise ValueError(f"등록되지 않은 접근 정책: {chunk.policy_id}")

        if chunk.source_type == "player_document":
            if chunk.source_id not in document_ids:
                raise ValueError(f"등록되지 않은 문서 ID: {chunk.source_id}")

        elif chunk.source_type == "npc_knowledge":
            if chunk.source_id not in npc_card_ids:
                raise ValueError(f"등록되지 않은 NPC 카드 ID: {chunk.source_id}")

        else:
            raise ValueError(f"지원하지 않는 원본 유형: {chunk.source_type}")

        if not chunk.content_hash.strip():
            raise ValueError(f"원본 해시가 비어 있습니다: {chunk.source_id}")

        if not chunk.search_text.strip():
            raise ValueError(f"검색 텍스트가 비어 있습니다: {chunk.source_id}")

        if not isinstance(record.parent_point_id, UUID):
            raise TypeError("parent_point_id는 UUID여야 합니다.")

        if (
            record.chunk_count < 1
            or record.chunk_index < 0
            or record.chunk_index >= record.chunk_count
        ):
            raise ValueError(f"청크 순서 오류: {chunk.source_id}")

        source_key = (
            chunk.source_type,
            chunk.source_id,
        )

        owner = parent_owners.setdefault(
            record.parent_point_id,
            source_key,
        )

        if owner != source_key:
            raise ValueError(f"원본 UUID 충돌: {record.parent_point_id}")

        sources[source_key].append(record)

    # 원본별 청크 개수 및 순서 검증
    for source_key, source_chunks in sources.items():
        expected_count = source_chunks[0].chunk_count
        expected_parent = source_chunks[0].parent_point_id
        expected_hash = source_chunks[0].chunk.content_hash

        for record in source_chunks:
            if record.chunk_count != expected_count:
                raise ValueError(f"청크 개수 불일치: {source_key}")

            if record.parent_point_id != expected_parent:
                raise ValueError(f"원본 UUID 불일치: {source_key}")

            if record.chunk.content_hash != expected_hash:
                raise ValueError(f"원본 해시 불일치: {source_key}")

        indices = sorted(record.chunk_index for record in source_chunks)

        if len(source_chunks) != expected_count or indices != list(
            range(expected_count)
        ):
            raise ValueError(f"청크 누락 또는 중복 순서: {source_key}")

    return VectorIntegrityReport(
        point_count=len(seen_points),
        source_count=len(sources),
    )


def validate_neo4j_records(
    *,
    entities: list[dict],
    relationships: list[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    events: list[SourceTimelineEvent],
    case_id: str = CASE_ID,
) -> GraphIntegrityReport:
    """Neo4j 적재 전 엔티티·관계·증거·사건을 검증한다."""

    if case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    # 기존 #14 검증 로직 재사용
    validate_graph_data(
        entities,
        relationships,
        case_id=case_id,
    )

    if not evidence_rules:
        raise ValueError("증거 규칙이 비어 있습니다.")

    entity_types = {entity["entity_id"]: entity["type"] for entity in entities}

    # 증거 ID와 보유자 참조 검증
    for evidence_id, rule in evidence_rules.items():
        if not EVIDENCE_ID_PATTERN.fullmatch(evidence_id):
            raise ValueError(f"잘못된 증거 ID: {evidence_id}")

        if not isinstance(rule, EvidenceRule):
            raise TypeError(f"검증되지 않은 증거 규칙: {evidence_id}")

        holder_id = rule.holder.strip()
        holder_type = entity_types.get(holder_id)

        if holder_type not in ALLOWED_HOLDER_TYPES:
            raise ValueError(f"증거 보유자 참조 오류: {evidence_id} -> {holder_id}")

        # 기존 엔티티와 증거 ID가 충돌하는지 확인
        existing_type = entity_types.get(evidence_id)

        if existing_type is not None and existing_type != "Evidence":
            raise ValueError(f"증거 엔티티 유형 충돌: {evidence_id}")

    # 관계가 요구하는 증거 ID가 실제 존재하는지 확인
    for edge in relationships:
        for evidence_id in edge.required_evidence:
            if evidence_id not in evidence_rules:
                raise ValueError(
                    f"관계 증거 참조 오류: {edge.edge_id} -> {evidence_id}"
                )

    # 관리자 타임라인의 사건 ID 및 엔티티 참조 검증
    event_rows, mention_rows = build_admin_graph_rows(
        events,
        entities,
    )

    return GraphIntegrityReport(
        entity_count=len(entities),
        relationship_count=len(relationships),
        evidence_count=len(evidence_rules),
        event_count=len(event_rows),
        mention_count=len(mention_rows),
    )
