"""CASE-001 Qdrant 데이터 동기화 및 변경사항 검증."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from crimescene.db.ingest_integrity import validate_qdrant_records
from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_points import build_qdrant_point
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder

CASE_ID = "CASE-001"
MANAGED_SOURCE_TYPES = ("player_document", "npc_knowledge")


@dataclass(frozen=True)
class QdrantSyncPlan:
    """동기화 예정 작업. ID만 반환해 비공개 본문 노출을 방지한다."""

    added: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    deleted: tuple[str, ...]

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.updated) + len(self.deleted)


def _expected_payload(record: HybridChunkRecord) -> dict:
    """현재 Qdrant Point 저장 규격과 동일한 메타데이터."""

    chunk = record.chunk

    return {
        "source_id": chunk.source_id,
        "source_type": chunk.source_type,
        "case_id": chunk.case_id,
        "policy_id": chunk.policy_id,
        "family": chunk.family,
        "access_scope": chunk.access_scope,
        "character_id": chunk.character_id,
        "incident_year": chunk.incident_year,
        "content_hash": chunk.content_hash,
        "search_text": chunk.search_text,
        "body": chunk.body,
        "parent_point_id": str(record.parent_point_id),
        "chunk_index": record.chunk_index,
        "chunk_count": record.chunk_count,
    }


def _existing_case_points(
    client: QdrantClient,
    collection_name: str,
) -> dict:
    """현재 CASE-001에 속한 관리 대상 Point를 모두 조회한다."""

    case_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="case_id",
                match=models.MatchValue(value=CASE_ID),
            ),
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(any=list(MANAGED_SOURCE_TYPES)),
            ),
        ]
    )

    points = {}
    offset = None

    while True:
        batch, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=case_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in batch:
            point_id = str(point.id)

            if point_id in points:
                raise ValueError(f"중복 조회된 Qdrant Point: {point_id}")

            points[point_id] = point

        if next_offset is None:
            break

        if next_offset == offset:
            raise RuntimeError("Qdrant Scroll 페이지가 진행되지 않습니다.")

        offset = next_offset

    return points


def _check_point_collisions(
    client: QdrantClient,
    collection_name: str,
    records: list[HybridChunkRecord],
) -> None:
    """다른 사건이나 원본이 소유한 UUID의 덮어쓰기를 차단한다."""

    record_map = {record.chunk.point_id: record for record in records}

    ids = sorted(record_map)

    for start in range(0, len(ids), 128):
        batch_ids = ids[start : start + 128]

        existing = client.retrieve(
            collection_name=collection_name,
            ids=batch_ids,
            with_payload=True,
            with_vectors=False,
        )

        for point in existing:
            point_id = str(point.id)
            payload = point.payload or {}
            expected = record_map[point_id].chunk

            if payload.get("case_id") != CASE_ID:
                raise ValueError(f"다른 사건의 Point UUID 충돌: {point_id}")

            if (
                payload.get("source_id") != expected.source_id
                or payload.get("source_type") != expected.source_type
            ):
                raise ValueError(f"다른 원본의 Point UUID 충돌: {point_id}")


def _build_plan(
    client: QdrantClient,
    records: list[HybridChunkRecord],
    collection_name: str,
) -> QdrantSyncPlan:
    """실제 DB 상태와 신규 데이터의 차이를 계산한다."""

    expected = {record.chunk.point_id: record for record in records}

    existing = _existing_case_points(
        client,
        collection_name,
    )

    _check_point_collisions(
        client,
        collection_name,
        records,
    )

    added = []
    updated = []
    unchanged = []

    for point_id, record in sorted(expected.items()):
        current = existing.get(point_id)

        if current is None:
            added.append(point_id)

        elif (current.payload or {}) != _expected_payload(record):
            updated.append(point_id)

        else:
            unchanged.append(point_id)

    deleted = sorted(set(existing) - set(expected))

    return QdrantSyncPlan(
        added=tuple(added),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
        deleted=tuple(deleted),
    )


def sync_qdrant_records(
    records: Iterable[HybridChunkRecord],
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    document_ids: Collection[str],
    npc_card_ids: Collection[str],
    valid_policy_ids: Collection[str],
    collection_name: str = COLLECTION_NAME,
    dry_run: bool = True,
    allow_delete: bool = False,
) -> QdrantSyncPlan:
    """CASE-001 원본 스냅샷으로 Qdrant를 동기화한다.

    기본값은 읽기 전용 Dry Run이다.

    삭제는 전체 원본 스냅샷이 전달되었음을 확인한 뒤
    allow_delete=True로 명시적으로 승인해야 한다.

    다른 사건의 Point는 변경하지 않는다.
    """

    if not isinstance(dry_run, bool):
        raise TypeError("dry_run은 bool이어야 합니다.")

    if not isinstance(allow_delete, bool):
        raise TypeError("allow_delete는 bool이어야 합니다.")

    source_records = list(records)

    # 1. DB 작업 이전에 원본 무결성 검증
    validate_qdrant_records(
        source_records,
        document_ids=document_ids,
        npc_card_ids=npc_card_ids,
        valid_policy_ids=valid_policy_ids,
    )

    if not client.collection_exists(collection_name):
        raise ValueError(f"Qdrant 컬렉션이 존재하지 않습니다: {collection_name}")

    # 컬렉션 Vector 설정 확인
    ensure_qdrant_collection(
        client,
        collection_name=collection_name,
    )

    # 2. 변경 계획 생성
    plan = _build_plan(
        client,
        source_records,
        collection_name,
    )

    # Dry Run에서는 DB를 수정하지 않음
    if dry_run:
        return plan

    # 3. 삭제가 필요한 경우 명시적 승인 요구
    if plan.deleted and not allow_delete:
        raise ValueError(
            f"삭제 예정 Point {len(plan.deleted)}개가 존재합니다. "
            "적용하려면 allow_delete=True가 필요합니다."
        )

    # 4. 추가·수정할 Point만 선택
    changed_ids = set(plan.added) | set(plan.updated)

    changed_records = [
        record for record in source_records if record.chunk.point_id in changed_ids
    ]

    # 5. 임베딩과 Point 검증을 모두 완료한 뒤 DB에 저장
    # 임베딩 도중 실패하면 삭제나 Upsert를 실행하지 않음
    if changed_records:
        vectors = embedder.embed_texts(
            [record.chunk.search_text for record in changed_records]
        )

        if len(vectors) != len(changed_records):
            raise ValueError("청크 개수와 임베딩 개수가 일치하지 않습니다.")

        points = [
            build_qdrant_point(record, vector)
            for record, vector in zip(
                changed_records,
                vectors,
                strict=True,
            )
        ]

        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

    # 6. 추가·수정이 성공한 뒤 오래된 Point 삭제
    if plan.deleted:
        client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=list(plan.deleted)),
            wait=True,
        )

    # 7. 최종 DB 상태 검증
    actual = _existing_case_points(
        client,
        collection_name,
    )

    expected_ids = {record.chunk.point_id for record in source_records}

    if set(actual) != expected_ids:
        raise RuntimeError("동기화 후 Qdrant Point ID가 원본과 일치하지 않습니다.")

    for record in source_records:
        point_id = record.chunk.point_id

        if (actual[point_id].payload or {}) != _expected_payload(record):
            raise RuntimeError(f"동기화 후 Point 메타데이터 불일치: {point_id}")

    return plan
