"""RAG 청크를 Qdrant Point로 변환한다."""

import math
from collections.abc import Sequence

from qdrant_client import models

from crimescene.db.qdrant_collection import (
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
)
from crimescene.ingest.hybrid_chunker import HybridChunkRecord


def build_qdrant_point(
    record: HybridChunkRecord,
    dense_vector: Sequence[float],
) -> models.PointStruct:
    """Hybrid 청크와 Dense Vector를 Qdrant Point로 변환한다.

    관리자 전용 메타데이터는 Payload에 포함하지 않는다.
    이 함수는 접근 권한 승인을 수행하지 않는다.
    """

    if not isinstance(record, HybridChunkRecord):
        raise TypeError("HybridChunkRecord 타입이 필요합니다.")

    if isinstance(dense_vector, (str, bytes)) or not isinstance(dense_vector, Sequence):
        raise TypeError("Dense Vector는 숫자 시퀀스여야 합니다.")

    # 1. 벡터 값 변환
    try:
        vector = [float(value) for value in dense_vector]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("유효하지 않은 Dense Vector 값입니다.") from exc

    # 2. 벡터 차원 확인
    if len(vector) != DENSE_VECTOR_SIZE:
        raise ValueError("Dense Vector 차원이 일치하지 않습니다.")

    # 3. NaN / Infinity 차단
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("유효하지 않은 Dense Vector 값입니다.")

    # 4. 영벡터 차단
    if not any(value != 0.0 for value in vector):
        raise ValueError("영벡터는 저장할 수 없습니다.")

    chunk = record.chunk

    # 5. 청크 순서 검증
    if (
        record.chunk_count < 1
        or record.chunk_index < 0
        or record.chunk_index >= record.chunk_count
    ):
        raise ValueError("청크 순서 정보가 올바르지 않습니다.")

    # 6. 허용된 메타데이터만 명시적으로 등록
    payload = {
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

    # 7. Qdrant Point 생성
    return models.PointStruct(
        id=chunk.point_id,
        vector={
            DENSE_VECTOR_NAME: vector,
        },
        payload=payload,
    )
