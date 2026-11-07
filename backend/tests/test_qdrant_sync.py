"""Qdrant 데이터 동기화 테스트."""

from dataclasses import replace
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_SIZE,
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_points import build_qdrant_point
from crimescene.db.qdrant_sync import sync_qdrant_records
from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder


@pytest.fixture
def client():
    """실제 DB와 분리된 인메모리 Qdrant."""

    db = QdrantClient(":memory:")
    ensure_qdrant_collection(db)

    yield db

    db.close()


@pytest.fixture
def embedder():
    """Ollama 호출 없이 테스트용 임베딩 생성."""

    mock = Mock(spec=OllamaEmbedder)

    mock.embed_texts.side_effect = lambda texts: [
        [0.1] * DENSE_VECTOR_SIZE for _ in texts
    ]

    return mock


def make_record(index):
    point_id = uuid5(
        NAMESPACE_URL,
        f"CASE-001-SYNC-{index}",
    )

    chunk = RAGChunk(
        chunk_id=point_id,
        source_id=f"DOC-{index:03d}",
        source_type="player_document",
        case_id="CASE-001",
        policy_id="POL-TEST-001",
        family="evidence",
        access_scope="collected_evidence",
        character_id=None,
        incident_year=2026,
        content_hash=f"hash-{index}",
        search_text=f"테스트 문서 {index}",
        body=f"테스트 문서 {index}",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=point_id,
        chunk_index=0,
        chunk_count=1,
    )


def run_sync(client, embedder, records, **kwargs):
    return sync_qdrant_records(
        records,
        client=client,
        embedder=embedder,
        document_ids={f"DOC-{i:03d}" for i in range(1, 100)},
        npc_card_ids=set(),
        valid_policy_ids={"POL-TEST-001"},
        **kwargs,
    )


def point_count(client):
    return client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count


def test_dry_run_does_not_write(client, embedder):
    """Dry Run은 DB를 수정하지 않는다."""

    plan = run_sync(
        client,
        embedder,
        [make_record(1)],
    )

    assert len(plan.added) == 1
    assert plan.total_changes == 1
    assert point_count(client) == 0
    embedder.embed_texts.assert_not_called()


def test_initial_sync(client, embedder):
    """최초 적재 시 새 청크를 저장한다."""

    plan = run_sync(
        client,
        embedder,
        [make_record(1), make_record(2)],
        dry_run=False,
    )

    assert len(plan.added) == 2
    assert point_count(client) == 2


def test_repeated_sync_is_idempotent(client, embedder):
    """동일 데이터 재실행 시 변경사항이 없다."""

    records = [make_record(1), make_record(2)]

    run_sync(
        client,
        embedder,
        records,
        dry_run=False,
    )

    embedder.embed_texts.reset_mock()

    plan = run_sync(
        client,
        embedder,
        records,
        dry_run=False,
    )

    assert plan.total_changes == 0
    assert len(plan.unchanged) == 2
    assert point_count(client) == 2

    embedder.embed_texts.assert_not_called()


def test_modified_document_updates(client, embedder):
    """문서 내용 변경 시 동일 UUID를 갱신한다."""

    original = make_record(1)

    run_sync(
        client,
        embedder,
        [original],
        dry_run=False,
    )

    updated = replace(
        original,
        chunk=original.chunk.model_copy(
            update={
                "body": "수정된 사건 기록",
                "search_text": "수정된 사건 기록",
                "content_hash": "updated-hash",
            }
        ),
    )

    plan = run_sync(
        client,
        embedder,
        [updated],
        dry_run=False,
    )

    assert len(plan.updated) == 1
    assert point_count(client) == 1

    stored = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[original.chunk.point_id],
        with_payload=True,
    )

    assert stored[0].payload["body"] == "수정된 사건 기록"


def test_deletion_requires_approval(client, embedder):
    """삭제 대상이 있으면 명시적 승인을 요구한다."""

    run_sync(
        client,
        embedder,
        [make_record(1), make_record(2)],
        dry_run=False,
    )

    with pytest.raises(ValueError, match="allow_delete"):
        run_sync(
            client,
            embedder,
            [make_record(1)],
            dry_run=False,
        )

    assert point_count(client) == 2


def test_deleted_document_removed(client, embedder):
    """승인 후 삭제된 문서의 Point를 제거한다."""

    run_sync(
        client,
        embedder,
        [make_record(1), make_record(2)],
        dry_run=False,
    )

    plan = run_sync(
        client,
        embedder,
        [make_record(1)],
        dry_run=False,
        allow_delete=True,
    )

    assert len(plan.deleted) == 1
    assert point_count(client) == 1


def test_embedding_failure_preserves_old_data(client, embedder):
    """임베딩 실패 시 기존 데이터는 삭제되지 않는다."""

    original = make_record(1)
    stale = make_record(2)

    run_sync(
        client,
        embedder,
        [original, stale],
        dry_run=False,
    )

    changed = replace(
        original,
        chunk=original.chunk.model_copy(
            update={
                "body": "변경된 내용",
                "search_text": "변경된 내용",
            }
        ),
    )

    embedder.embed_texts.side_effect = RuntimeError("Embedding failed")

    with pytest.raises(RuntimeError, match="Embedding failed"):
        run_sync(
            client,
            embedder,
            [changed],
            dry_run=False,
            allow_delete=True,
        )

    assert point_count(client) == 2


def test_other_case_is_preserved(client, embedder):
    """다른 사건의 데이터는 삭제하지 않는다."""

    foreign = make_record(99)

    point = build_qdrant_point(
        foreign,
        [0.1] * DENSE_VECTOR_SIZE,
    )

    point.payload["case_id"] = "CASE-999"

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
        wait=True,
    )

    run_sync(
        client,
        embedder,
        [make_record(1)],
        dry_run=False,
        allow_delete=True,
    )

    assert point_count(client) == 2


def test_cross_case_uuid_collision_rejected(client, embedder):
    """다른 사건과 UUID가 충돌하면 적재를 중단한다."""

    record = make_record(1)

    point = build_qdrant_point(
        record,
        [0.1] * DENSE_VECTOR_SIZE,
    )

    point.payload["case_id"] = "CASE-999"

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
        wait=True,
    )

    with pytest.raises(ValueError, match="다른 사건"):
        run_sync(
            client,
            embedder,
            [record],
            dry_run=False,
        )

    assert point_count(client) == 1


def test_duplicate_input_rejected(client, embedder):
    """동일 UUID가 입력에 중복되면 차단한다."""

    record = make_record(1)

    with pytest.raises(ValueError, match="중복"):
        run_sync(
            client,
            embedder,
            [record, record],
            dry_run=False,
        )

    assert point_count(client) == 0
