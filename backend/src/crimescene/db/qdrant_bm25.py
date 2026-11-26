"""Issue #175 - corpus-consistent Qdrant BM25 vectors."""

import math

from qdrant_client import models

from crimescene.db.qdrant_collection import SPARSE_VECTOR_NAME
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder


def validate_sparse_vector(vector):
    if not isinstance(vector, models.SparseVector):
        raise TypeError("SparseVector required")

    if (
        not vector.indices
        or len(vector.indices) != len(vector.values)
        or len(set(vector.indices)) != len(vector.indices)
    ):
        raise ValueError("Invalid sparse vector dimensions")

    if any(
        type(index) is not int
        or not 0 <= index <= 4294967295
        for index in vector.indices
    ):
        raise ValueError("Invalid sparse vector index")

    if any(
        not math.isfinite(value) or value <= 0
        for value in vector.values
    ):
        raise ValueError("Invalid sparse vector weight")


def build_corpus_sparse_vectors(records):
    records = tuple(records)

    if not records:
        return {}

    ids = [record.chunk.point_id for record in records]

    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate corpus point ID")

    encoder = KoreanBM25Encoder()

    vectors = encoder.encode_documents([
        record.chunk.search_text
        for record in records
    ])

    result = dict(zip(ids, vectors, strict=True))

    for vector in result.values():
        validate_sparse_vector(vector)

    return result


def sparse_vectors_match(actual, expected):
    try:
        validate_sparse_vector(actual)
        validate_sparse_vector(expected)
    except (TypeError, ValueError):
        return False

    actual_map = dict(zip(
        actual.indices,
        actual.values,
        strict=True,
    ))

    expected_map = dict(zip(
        expected.indices,
        expected.values,
        strict=True,
    ))

    return (
        actual_map.keys() == expected_map.keys()
        and all(
            math.isclose(
                actual_map[index],
                weight,
                rel_tol=1e-6,
                abs_tol=1e-7,
            )
            for index, weight in expected_map.items()
        )
    )


def find_sparse_mismatches(
    client,
    collection_name,
    point_ids,
    expected,
):
    ids = sorted(point_ids)
    mismatches = []
    seen = set()

    for start in range(0, len(ids), 128):
        batch = ids[start:start + 128]

        points = client.retrieve(
            collection_name=collection_name,
            ids=batch,
            with_payload=False,
            with_vectors=[SPARSE_VECTOR_NAME],
        )

        batch_seen = set()

        for point in points:
            point_id = str(point.id)

            if point_id not in batch or point_id in seen:
                raise ValueError("Unexpected sparse point")

            seen.add(point_id)
            batch_seen.add(point_id)

            actual = (
                point.vector.get(SPARSE_VECTOR_NAME)
                if isinstance(point.vector, dict)
                else None
            )

            if not sparse_vectors_match(
                actual,
                expected[point_id],
            ):
                mismatches.append(point_id)

        if batch_seen != set(batch):
            raise RuntimeError("Sparse point coverage mismatch")

    return tuple(sorted(mismatches))
