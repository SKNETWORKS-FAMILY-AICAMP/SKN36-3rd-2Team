"""Qdrant 컬렉션 생성 및 설정 검증 테스트."""

import pytest
from qdrant_client import QdrantClient, models

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    SPARSE_VECTOR_NAME,
    ensure_qdrant_collection,
)


@pytest.fixture
def client():
    """실제 Docker와 분리된 인메모리 Qdrant."""

    qdrant = QdrantClient(":memory:")

    yield qdrant

    qdrant.close()


def test_create_collection(client):
    """새로운 컬렉션을 생성한다."""

    created = ensure_qdrant_collection(client)

    assert created is True
    assert client.collection_exists(COLLECTION_NAME)


def test_dense_vector_configuration(client):
    """Dense Vector 차원과 Cosine 설정을 확인한다."""

    ensure_qdrant_collection(client)

    info = client.get_collection(COLLECTION_NAME)
    vectors = info.config.params.vectors

    assert isinstance(vectors, dict)
    assert DENSE_VECTOR_NAME in vectors

    dense = vectors[DENSE_VECTOR_NAME]

    assert dense.size == DENSE_VECTOR_SIZE
    assert dense.distance == models.Distance.COSINE


def test_sparse_vector_configuration(client):
    """Sparse Vector 및 IDF 설정을 확인한다."""

    ensure_qdrant_collection(client)

    info = client.get_collection(COLLECTION_NAME)

    sparse = info.config.params.sparse_vectors

    assert sparse is not None
    assert SPARSE_VECTOR_NAME in sparse
    assert sparse[SPARSE_VECTOR_NAME].modifier == models.Modifier.IDF


def test_existing_collection_reused(client):
    """기존 컬렉션을 다시 생성하지 않는다."""

    first = ensure_qdrant_collection(client)
    second = ensure_qdrant_collection(client)

    assert first is True
    assert second is False


def test_existing_points_preserved(client):
    """컬렉션 확인 과정에서 저장된 데이터를 삭제하지 않는다."""

    ensure_qdrant_collection(client)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=1,
                vector={
                    DENSE_VECTOR_NAME: [0.1] * DENSE_VECTOR_SIZE,
                },
                payload={"source_id": "DOC-TEST-001"},
            )
        ],
        wait=True,
    )

    assert ensure_qdrant_collection(client) is False

    points = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[1],
        with_payload=True,
    )

    assert len(points) == 1
    assert points[0].payload == {"source_id": "DOC-TEST-001"}


def test_invalid_dense_dimension_rejected(client):
    """다른 차원의 컬렉션을 거부한다."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=768,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            )
        },
    )

    with pytest.raises(
        ValueError,
        match="차원이 일치하지 않습니다",
    ):
        ensure_qdrant_collection(client)


def test_invalid_distance_rejected(client):
    """Cosine이 아닌 유사도 설정을 거부한다."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.DOT,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            )
        },
    )

    with pytest.raises(
        ValueError,
        match="유사도 설정이 일치하지 않습니다",
    ):
        ensure_qdrant_collection(client)


def test_missing_dense_vector_rejected(client):
    """Dense Vector 이름이 일치하지 않으면 거부한다."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "other_dense": models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            )
        },
    )

    with pytest.raises(
        ValueError,
        match="Dense Vector 설정이 없습니다",
    ):
        ensure_qdrant_collection(client)


def test_missing_sparse_vector_rejected(client):
    """Sparse Vector 설정이 없으면 거부한다."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            )
        },
    )

    with pytest.raises(
        ValueError,
        match="Sparse Vector 설정이 없습니다",
    ):
        ensure_qdrant_collection(client)


def test_missing_sparse_idf_rejected(client):
    """Sparse IDF 설정이 없으면 거부한다."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )

    with pytest.raises(
        ValueError,
        match="Sparse IDF 설정이 일치하지 않습니다",
    ):
        ensure_qdrant_collection(client)


@pytest.mark.parametrize(
    "name",
    ["", "   "],
)
def test_empty_collection_name_rejected(client, name):
    """빈 컬렉션 이름을 거부한다."""

    with pytest.raises(
        ValueError,
        match="컬렉션 이름이 비어 있습니다",
    ):
        ensure_qdrant_collection(
            client,
            collection_name=name,
        )


def test_invalid_collection_name_type_rejected(client):
    """문자열이 아닌 컬렉션 이름을 거부한다."""

    with pytest.raises(
        TypeError,
        match="컬렉션 이름은 문자열",
    ):
        ensure_qdrant_collection(
            client,
            collection_name=123,
        )


def test_custom_collection_name(client):
    """별도로 지정한 컬렉션 이름도 지원한다."""

    name = "case001_rag_test"

    created = ensure_qdrant_collection(
        client,
        collection_name=name,
    )

    assert created is True
    assert client.collection_exists(name)
