"""CASE-001 Qdrant 컬렉션 생성 및 설정 검증."""

from qdrant_client import QdrantClient, models

COLLECTION_NAME = "case001_rag_v1"

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"

DENSE_VECTOR_SIZE = 1024


def ensure_qdrant_collection(
    client: QdrantClient,
    *,
    collection_name: str = COLLECTION_NAME,
) -> bool:
    """Qdrant 컬렉션을 생성하거나 기존 설정을 검증한다.

    Returns:
        True: 신규 컬렉션 생성
        False: 기존 컬렉션 검증 완료

    기존 컬렉션은 삭제하거나 초기화하지 않는다.
    """

    if not isinstance(collection_name, str):
        raise TypeError("컬렉션 이름은 문자열이어야 합니다.")

    if not collection_name.strip():
        raise ValueError("컬렉션 이름이 비어 있습니다.")

    # 1. 기존 컬렉션 확인
    if client.collection_exists(collection_name):
        info = client.get_collection(collection_name)

        params = info.config.params

        # 2. Dense Vector 설정 검증
        vectors = params.vectors

        if not isinstance(vectors, dict) or DENSE_VECTOR_NAME not in vectors:
            raise ValueError("기존 컬렉션에 Dense Vector 설정이 없습니다.")

        dense_config = vectors[DENSE_VECTOR_NAME]

        if dense_config.size != DENSE_VECTOR_SIZE:
            raise ValueError("기존 컬렉션의 Dense Vector 차원이 일치하지 않습니다.")

        if dense_config.distance != models.Distance.COSINE:
            raise ValueError("기존 컬렉션의 유사도 설정이 일치하지 않습니다.")

        # 3. Sparse Vector 설정 검증
        sparse_vectors = params.sparse_vectors or {}

        if SPARSE_VECTOR_NAME not in sparse_vectors:
            raise ValueError("기존 컬렉션에 Sparse Vector 설정이 없습니다.")

        sparse_config = sparse_vectors[SPARSE_VECTOR_NAME]

        if sparse_config.modifier != models.Modifier.IDF:
            raise ValueError("기존 컬렉션의 Sparse IDF 설정이 일치하지 않습니다.")

        return False

    # 4. 신규 컬렉션 생성
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
    )

    return True
