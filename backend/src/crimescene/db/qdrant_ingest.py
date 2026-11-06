"""BGE-M3 임베딩 및 Qdrant 벡터 적재 파이프라인."""

from collections.abc import Iterable
from uuid import UUID

from qdrant_client import QdrantClient

from crimescene.db.qdrant_collection import (
    COLLECTION_NAME,
    ensure_qdrant_collection,
)
from crimescene.db.qdrant_points import build_qdrant_point
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder

DEFAULT_INGEST_BATCH_SIZE = 16


def upsert_hybrid_records(
    records: Iterable[HybridChunkRecord],
    *,
    client: QdrantClient,
    embedder: OllamaEmbedder,
    collection_name: str = COLLECTION_NAME,
    batch_size: int = DEFAULT_INGEST_BATCH_SIZE,
) -> int:
    """Hybrid 청크를 임베딩하여 Qdrant에 적재한다.

    Args:
        records: 검증된 Hybrid 청크 목록
        client: Qdrant 클라이언트
        embedder: Ollama 임베딩 생성기
        collection_name: 적재할 컬렉션
        batch_size: 한 번에 처리할 청크 개수

    Returns:
        정상적으로 Upsert한 Point 개수

    주의:
        접근 권한이 없는 문서도 내부 인덱스에
        존재할 수 있으므로 검색 후 권한 검사가 필수이다.
    """

    # 1. Batch 크기 검증
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("Batch 크기는 정수여야 합니다.")

    if batch_size <= 0:
        raise ValueError("Batch 크기는 양수여야 합니다.")

    # 2. 컬렉션 이름 검증
    if not isinstance(collection_name, str):
        raise TypeError("컬렉션 이름은 문자열이어야 합니다.")

    if not collection_name.strip():
        raise ValueError("컬렉션 이름이 비어 있습니다.")

    # 3. 입력 청크 목록 생성
    source_records = list(records)

    if not source_records:
        raise ValueError("적재할 청크가 없습니다.")

    # 4. 전체 입력을 먼저 검증
    seen_ids: set[UUID] = set()

    for record in source_records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("HybridChunkRecord 타입만 적재할 수 있습니다.")

        point_id = record.chunk.chunk_id

        if point_id in seen_ids:
            raise ValueError(f"중복된 청크 UUID: {point_id}")

        seen_ids.add(point_id)

        if not record.chunk.search_text.strip():
            raise ValueError("임베딩할 검색 텍스트가 비어 있습니다.")

    # 5. Qdrant 컬렉션 확인
    if not client.collection_exists(collection_name):
        raise ValueError(f"Qdrant 컬렉션이 존재하지 않습니다: {collection_name}")

    # 기존 Dense / Sparse 설정 검증
    ensure_qdrant_collection(
        client,
        collection_name=collection_name,
    )

    total_upserted = 0

    # 6. Batch 단위로 임베딩 및 적재
    for start in range(
        0,
        len(source_records),
        batch_size,
    ):
        batch = source_records[start : start + batch_size]

        texts = [record.chunk.search_text for record in batch]

        # 7. BGE-M3 임베딩 생성
        vectors = embedder.embed_texts(texts)

        if len(vectors) != len(batch):
            raise ValueError("청크 개수와 임베딩 개수가 일치하지 않습니다.")

        # 8. Qdrant Point 생성
        points = [
            build_qdrant_point(record, vector)
            for record, vector in zip(
                batch,
                vectors,
                strict=True,
            )
        ]

        # 9. Qdrant 저장
        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

        total_upserted += len(points)

    return total_upserted
