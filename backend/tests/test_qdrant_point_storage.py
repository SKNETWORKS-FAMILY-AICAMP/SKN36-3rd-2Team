"""Qdrant Point 저장 및 조회 통합 테스트."""

import math
from uuid import UUID

import pytest
from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_points import build_qdrant_point
from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord

DOC_POINT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")

NPC_POINT_ID = UUID("550e8400-e29b-41d4-a716-446655440001")


@pytest.fixture
def client():
    """실제 Docker와 분리된 인메모리 Qdrant."""

    qdrant = QdrantClient(":memory:")

    ensure_qdrant_collection(qdrant)

    yield qdrant

    qdrant.close()


def make_record(*, npc=False):
    """테스트용 HybridChunkRecord 생성."""

    if npc:
        point_id = NPC_POINT_ID
        source_id = "K-C01-001"
        source_type = "npc_knowledge"
        family = "npc_knowledge"
        access_scope = "character_only"
        character_id = "C01"
    else:
        point_id = DOC_POINT_ID
        source_id = "DOC-TEST-001"
        source_type = "player_document"
        family = "evidence"
        access_scope = "collected_evidence"
        character_id = None

    chunk = RAGChunk(
        chunk_id=point_id,
        source_id=source_id,
        source_type=source_type,
        case_id="CASE-001",
        policy_id="POL-TEST-001",
        family=family,
        access_scope=access_scope,
        character_id=character_id,
        incident_year=2016,
        content_hash="test-content-hash",
        search_text="사건 당일의 기록",
        body="사건 당일의 기록",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=point_id,
        chunk_index=0,
        chunk_count=1,
    )


def make_point(record):
    """기존 Point 변환 모듈을 사용한다."""

    vector = [0.1] * DENSE_VECTOR_SIZE

    return build_qdrant_point(record, vector)


def test_point_upsert_and_retrieve(client):
    """Point를 저장하고 UUID로 다시 조회한다."""

    record = make_record()
    point = make_point(record)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
        wait=True,
    )

    results = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[record.chunk.point_id],
        with_payload=True,
    )

    assert len(results) == 1
    assert str(results[0].id) == record.chunk.point_id


def test_payload_metadata_preserved(client):
    """저장 후 접근 정책 메타데이터를 유지한다."""

    record = make_record()

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[make_point(record)],
        wait=True,
    )

    results = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[record.chunk.point_id],
        with_payload=True,
    )

    payload = results[0].payload

    assert payload is not None

    assert payload["source_id"] == "DOC-TEST-001"
    assert payload["case_id"] == "CASE-001"
    assert payload["policy_id"] == "POL-TEST-001"
    assert payload["access_scope"] == "collected_evidence"
    assert payload["parent_point_id"] == str(DOC_POINT_ID)

    forbidden = {
        "admin_truth",
        "protected_fact_ids",
        "source_refs",
        "supersedes",
        "stage_priority",
    }

    assert not forbidden.intersection(payload)


def test_dense_vector_saved(client):
    """Dense Vector가 1,024차원으로 저장된다."""

    record = make_record()

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[make_point(record)],
        wait=True,
    )

    results = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[record.chunk.point_id],
        with_vectors=True,
    )

    assert len(results) == 1

    vectors = results[0].vector

    assert isinstance(vectors, dict)
    assert DENSE_VECTOR_NAME in vectors

    dense = vectors[DENSE_VECTOR_NAME]

    assert len(dense) == 1024
    assert all(math.isfinite(value) for value in dense)


def test_multiple_points_upsert(client):
    """플레이어 문서와 NPC 지식을 함께 저장한다."""

    document = make_record()
    npc = make_record(npc=True)

    points = [
        make_point(document),
        make_point(npc),
    ]

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )

    result = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    )

    assert result.count == 2


def test_repeated_upsert_is_idempotent(client):
    """같은 UUID를 다시 저장해도 Point가 중복되지 않는다."""

    record = make_record()
    point = make_point(record)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
        wait=True,
    )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
        wait=True,
    )

    result = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    )

    assert result.count == 1


def test_npc_point_metadata_preserved(client):
    """NPC 지식의 인물 및 공개 범위가 유지된다."""

    npc = make_record(npc=True)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[make_point(npc)],
        wait=True,
    )

    results = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[npc.chunk.point_id],
        with_payload=True,
    )

    assert len(results) == 1

    payload = results[0].payload

    assert payload is not None

    assert payload["source_type"] == "npc_knowledge"
    assert payload["character_id"] == "C01"
    assert payload["access_scope"] == "character_only"
    assert payload["policy_id"] == "POL-TEST-001"
