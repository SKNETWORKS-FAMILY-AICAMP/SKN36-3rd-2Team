"""BGE-M3 임베딩 및 Qdrant 적재 파이프라인 테스트."""

from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_SIZE,
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_ingest import upsert_hybrid_records
from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder


@pytest.fixture
def client():
    """실제 Docker와 분리된 인메모리 Qdrant."""

    qdrant = QdrantClient(":memory:")
    ensure_qdrant_collection(qdrant)

    yield qdrant

    qdrant.close()


@pytest.fixture
def embedder():
    """실제 Ollama를 호출하지 않는 임베딩 Mock."""

    mock = Mock(spec=OllamaEmbedder)

    def fake_embed(texts):
        return [[float(index + 1)] * DENSE_VECTOR_SIZE for index, _ in enumerate(texts)]

    mock.embed_texts.side_effect = fake_embed

    return mock


def make_record(index: int) -> HybridChunkRecord:
    """고유 UUID를 가진 테스트 청크 생성."""

    point_id = uuid5(
        NAMESPACE_URL,
        f"CASE-001-INGEST-TEST-{index}",
    )

    chunk = RAGChunk(
        chunk_id=point_id,
        source_id=f"DOC-TEST-{index:03d}",
        source_type="player_document",
        case_id="CASE-001",
        policy_id="POL-TEST-001",
        family="evidence",
        access_scope="collected_evidence",
        character_id=None,
        incident_year=2016,
        content_hash=f"hash-{index}",
        search_text=f"사건 당일 기록 {index}",
        body=f"사건 당일 기록 {index}",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=point_id,
        chunk_index=0,
        chunk_count=1,
    )


def get_point_count(client: QdrantClient) -> int:
    """컬렉션에 저장된 Point 개수."""

    return client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count


def test_single_record_upsert(client, embedder):
    """청크 하나를 임베딩하고 Qdrant에 저장한다."""

    record = make_record(1)

    count = upsert_hybrid_records(
        [record],
        client=client,
        embedder=embedder,
    )

    assert count == 1
    assert get_point_count(client) == 1

    results = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[record.chunk.point_id],
        with_payload=True,
    )

    assert len(results) == 1

    payload = results[0].payload

    assert payload["source_id"] == "DOC-TEST-001"
    assert payload["policy_id"] == "POL-TEST-001"
    assert payload["access_scope"] == "collected_evidence"


def test_batch_processing(client, embedder):
    """Batch 크기에 따라 임베딩 요청을 분할한다."""

    records = [make_record(index) for index in range(5)]

    count = upsert_hybrid_records(
        records,
        client=client,
        embedder=embedder,
        batch_size=2,
    )

    assert count == 5
    assert get_point_count(client) == 5

    assert embedder.embed_texts.call_count == 3

    batch_sizes = [len(call.args[0]) for call in embedder.embed_texts.call_args_list]

    assert batch_sizes == [2, 2, 1]


def test_repeated_upsert_no_duplicates(client, embedder):
    """같은 UUID를 재적재해도 중복되지 않는다."""

    records = [
        make_record(1),
        make_record(2),
    ]

    first = upsert_hybrid_records(
        records,
        client=client,
        embedder=embedder,
    )

    second = upsert_hybrid_records(
        records,
        client=client,
        embedder=embedder,
    )

    assert first == 2
    assert second == 2
    assert get_point_count(client) == 2


def test_generator_input_supported(client, embedder):
    """Generator로 전달한 청크도 적재한다."""

    records = (make_record(index) for index in range(3))

    count = upsert_hybrid_records(
        records,
        client=client,
        embedder=embedder,
    )

    assert count == 3
    assert get_point_count(client) == 3


def test_missing_collection_rejected(embedder):
    """컬렉션이 없으면 자동 생성하지 않는다."""

    client = QdrantClient(":memory:")

    try:
        with pytest.raises(
            ValueError,
            match="컬렉션이 존재하지 않습니다",
        ):
            upsert_hybrid_records(
                [make_record(1)],
                client=client,
                embedder=embedder,
            )

        assert not client.collection_exists(COLLECTION_NAME)

    finally:
        client.close()


def test_empty_records_rejected(client, embedder):
    """적재할 청크가 없으면 거부한다."""

    with pytest.raises(
        ValueError,
        match="적재할 청크가 없습니다",
    ):
        upsert_hybrid_records(
            [],
            client=client,
            embedder=embedder,
        )

    embedder.embed_texts.assert_not_called()


@pytest.mark.parametrize(
    ("batch_size", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        ("2", TypeError),
    ],
)
def test_invalid_batch_size_rejected(
    client,
    embedder,
    batch_size,
    error_type,
):
    """잘못된 Batch 설정을 거부한다."""

    with pytest.raises(error_type):
        upsert_hybrid_records(
            [make_record(1)],
            client=client,
            embedder=embedder,
            batch_size=batch_size,
        )


def test_duplicate_uuid_rejected(client, embedder):
    """동일 UUID가 중복되면 적재 전에 거부한다."""

    record = make_record(1)

    with pytest.raises(
        ValueError,
        match="중복된 청크 UUID",
    ):
        upsert_hybrid_records(
            [record, record],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0
    embedder.embed_texts.assert_not_called()


def test_invalid_record_type_rejected(client, embedder):
    """HybridChunkRecord가 아닌 객체를 거부한다."""

    with pytest.raises(
        TypeError,
        match="HybridChunkRecord",
    ):
        upsert_hybrid_records(
            [make_record(1), "invalid"],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0


def test_empty_search_text_rejected(client, embedder):
    """빈 검색 텍스트를 가진 청크는 적재하지 않는다."""

    record = make_record(1)

    # 저장 경계의 방어 로직 검증을 위해
    # Pydantic 검증을 우회한 손상 객체를 구성한다.
    invalid_chunk = record.chunk.model_copy(update={"search_text": "   "})

    invalid_record = HybridChunkRecord(
        chunk=invalid_chunk,
        parent_point_id=record.parent_point_id,
        chunk_index=record.chunk_index,
        chunk_count=record.chunk_count,
    )

    with pytest.raises(
        ValueError,
        match="검색 텍스트가 비어 있습니다",
    ):
        upsert_hybrid_records(
            [invalid_record],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0


def test_embedding_count_mismatch(client, embedder):
    """임베딩 결과 개수가 다르면 적재하지 않는다."""

    embedder.embed_texts.side_effect = None
    embedder.embed_texts.return_value = [[0.1] * DENSE_VECTOR_SIZE]

    with pytest.raises(
        ValueError,
        match="임베딩 개수가 일치하지 않습니다",
    ):
        upsert_hybrid_records(
            [make_record(1), make_record(2)],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0


def test_ollama_error_propagated(client, embedder):
    """Ollama 오류 발생 시 저장하지 않고 오류를 전달한다."""

    embedder.embed_texts.side_effect = RuntimeError("Ollama unavailable")

    with pytest.raises(
        RuntimeError,
        match="Ollama unavailable",
    ):
        upsert_hybrid_records(
            [make_record(1)],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0


def test_invalid_embedding_dimension(client, embedder):
    """잘못된 차원의 벡터를 Qdrant에 저장하지 않는다."""

    embedder.embed_texts.side_effect = None
    embedder.embed_texts.return_value = [
        [0.1] * DENSE_VECTOR_SIZE,
        [0.1] * 768,
    ]

    with pytest.raises(
        ValueError,
        match="Dense Vector 차원이 일치하지 않습니다",
    ):
        upsert_hybrid_records(
            [make_record(1), make_record(2)],
            client=client,
            embedder=embedder,
        )

    assert get_point_count(client) == 0
