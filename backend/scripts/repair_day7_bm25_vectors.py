"""Issue #175 - repair missing BM25 vectors in the verified local release."""

import argparse
import hashlib
import json
import math

from collections import Counter
from datetime import datetime
from pathlib import Path

from qdrant_client import models

import evaluate_day7_evidence_dialogue as pilot

from crimescene.db.qdrant_collection import (
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    SPARSE_VECTOR_NAME,
)
from crimescene.db.qdrant_sync import _expected_payload
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder


COLLECTION = "case001_rag_1120_revision2"

PROTECTED_COLLECTIONS = (
    "case001_rag_v1",
    "case001_rag_1120_staging",
    "case001_rag_1120_revision1",
)

EXPECTED_POINTS = 138
BATCH_SIZE = 32


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def batches(items):
    for start in range(0, len(items), BATCH_SIZE):
        yield items[start:start + BATCH_SIZE]


def read_points(client, collection, ids):
    result = {}

    for batch in batches(sorted(ids)):
        points = client.retrieve(
            collection_name=collection,
            ids=batch,
            with_payload=True,
            with_vectors=True,
        )

        for point in points:
            point_id = str(point.id)

            require(
                point_id not in result,
                "Duplicate point returned",
            )

            result[point_id] = point

    require(
        set(result) == set(ids),
        "Qdrant point coverage mismatch",
    )

    return result


def protected_counts(client):
    result = {}

    for collection in PROTECTED_COLLECTIONS:
        if not client.collection_exists(collection):
            result[collection] = None
            continue

        result[collection] = client.count(
            collection_name=collection,
            exact=True,
        ).count

    return result


def validate_dense(point):
    vectors = point.vector

    require(
        isinstance(vectors, dict),
        "Named vectors required",
    )

    dense = vectors.get(DENSE_VECTOR_NAME)

    require(
        isinstance(dense, list)
        and len(dense) == DENSE_VECTOR_SIZE
        and all(math.isfinite(value) for value in dense)
        and any(value != 0.0 for value in dense),
        "Invalid existing dense vector",
    )

    return dense


def immutable_fingerprint(point):
    return digest({
        "id": str(point.id),
        "payload": point.payload,
        "dense": validate_dense(point),
    })


def validate_sparse(vector):
    require(
        isinstance(vector, models.SparseVector),
        "Invalid sparse vector type",
    )

    require(
        bool(vector.indices)
        and len(vector.indices) == len(vector.values),
        "Invalid sparse vector length",
    )

    require(
        len(set(vector.indices)) == len(vector.indices),
        "Duplicate sparse vector indices",
    )

    require(
        all(
            type(index) is int
            and 0 <= index <= 4294967295
            for index in vector.indices
        ),
        "Invalid sparse vector indices",
    )

    require(
        all(
            math.isfinite(value) and value > 0
            for value in vector.values
        ),
        "Invalid sparse vector weights",
    )


def sparse_matches(actual, expected):
    if not isinstance(actual, models.SparseVector):
        return False

    if len(actual.indices) != len(actual.values):
        return False

    if len(set(actual.indices)) != len(actual.indices):
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
        set(actual_map) == set(expected_map)
        and all(
            math.isclose(
                actual_map[index],
                value,
                rel_tol=1e-6,
                abs_tol=1e-7,
            )
            for index, value in expected_map.items()
        )
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly repair missing sparse vectors.",
    )

    args = parser.parse_args()

    token = (
        pilot.LOCAL
        / "case001_1120_release"
        / "service-token.txt"
    ).read_text(encoding="utf-8-sig").strip()

    require(bool(token), "Missing service token")

    with pilot.load_expanded_release_resources(
        catalog_path=(
            pilot.LOCAL
            / "case001_1120_runtime"
            / "catalog.draft.json"
        ),
        dataset_root=(
            pilot.LOCAL / "case001_1120_rag"
        ),
        token=token,
        release_version=pilot.RELEASE_VERSION,
    ) as resources:

        require(
            resources.content_version == "case001_1120",
            "Content version mismatch",
        )

        require(
            resources.collection_name == COLLECTION,
            "Collection mismatch",
        )

        client = resources.qdrant_client

        records = {
            str(record.chunk.point_id): record
            for record in resources.trusted_records
        }

        require(
            len(records) == EXPECTED_POINTS
            and len(records) == len(resources.trusted_records),
            "Unexpected source record count",
        )

        actual_count = client.count(
            collection_name=COLLECTION,
            exact=True,
        ).count

        require(
            actual_count == EXPECTED_POINTS,
            "Unexpected collection point count",
        )

        info = client.get_collection(COLLECTION)

        sparse_config = (
            info.config.params.sparse_vectors or {}
        )

        require(
            SPARSE_VECTOR_NAME in sparse_config
            and sparse_config[SPARSE_VECTOR_NAME].modifier
            == models.Modifier.IDF,
            "Unexpected BM25 collection configuration",
        )

        protected_before = protected_counts(client)

        points = read_points(
            client,
            COLLECTION,
            records,
        )

        fingerprints = {}

        for point_id, record in records.items():
            point = points[point_id]

            require(
                point.payload == _expected_payload(record),
                "Point payload mismatch",
            )

            fingerprints[point_id] = (
                immutable_fingerprint(point)
            )

        # Fit once against the complete trusted corpus.
        encoder = KoreanBM25Encoder()

        encoder.fit([
            record.chunk.search_text
            for record in records.values()
        ])

        expected_vectors = {}
        missing = []
        existing_valid = []
        existing_mismatch = []

        by_source_type = Counter()

        for point_id, record in records.items():
            vector = encoder.encode_document(
                record.chunk.search_text
            )

            validate_sparse(vector)

            expected_vectors[point_id] = vector

            actual = points[point_id].vector.get(
                SPARSE_VECTOR_NAME
            )

            if actual is None:
                missing.append(point_id)
                by_source_type[
                    record.chunk.source_type
                ] += 1

            elif sparse_matches(actual, vector):
                existing_valid.append(point_id)

            else:
                existing_mismatch.append(point_id)

        plan = {
            "collection": COLLECTION,
            "mode": (
                "APPLY" if args.apply else "DRY_RUN"
            ),
            "source_records": len(records),
            "collection_points": actual_count,
            "valid_dense_vectors": len(fingerprints),
            "existing_sparse_valid": len(existing_valid),
            "missing_sparse_vectors": len(missing),
            "existing_sparse_mismatch": len(existing_mismatch),
            "missing_by_source_type": dict(by_source_type),
            "avg_document_length": encoder.avg_document_length,
            "protected_collection_counts": protected_before,
            "planned_vector_updates": len(missing),
            "planned_point_deletes": 0,
            "planned_payload_updates": 0,
            "planned_dense_updates": 0,
        }

        print("\n===== BM25 REPAIR PLAN =====")
        print(json.dumps(plan, indent=2))

        require(
            not existing_mismatch,
            "Existing sparse vectors differ from expected corpus",
        )

        if not args.apply:
            print("\nDRY RUN ONLY")
            print("DATABASE WRITES: 0")
            print("SUCCESS: Repair plan validated.")
            return

        # Check the original state again before the first write.
        current = read_points(
            client,
            COLLECTION,
            records,
        )

        require(
            protected_counts(client) == protected_before,
            "Protected collection count changed",
        )

        for point_id, point in current.items():
            require(
                immutable_fingerprint(point)
                == fingerprints[point_id],
                "Point changed before repair",
            )

            actual = point.vector.get(SPARSE_VECTOR_NAME)

            if point_id in missing:
                require(
                    actual is None,
                    "Missing vector changed before repair",
                )
            else:
                require(
                    sparse_matches(
                        actual,
                        expected_vectors[point_id],
                    ),
                    "Existing sparse vector changed",
                )

        updates = [
            models.PointVectors(
                id=point_id,
                vector={
                    SPARSE_VECTOR_NAME:
                        expected_vectors[point_id],
                },
            )
            for point_id in sorted(missing)
        ]

        for batch in batches(updates):
            result = client.update_vectors(
                collection_name=COLLECTION,
                points=batch,
                wait=True,
            )

            require(
                result.status == models.UpdateStatus.COMPLETED,
                "Sparse vector update incomplete",
            )

            print(
                "UPDATED SPARSE VECTORS:",
                len(batch),
            )

        after = read_points(
            client,
            COLLECTION,
            records,
        )

        for point_id, point in after.items():
            require(
                immutable_fingerprint(point)
                == fingerprints[point_id],
                "Dense vector or payload changed",
            )

            require(
                sparse_matches(
                    point.vector.get(SPARSE_VECTOR_NAME),
                    expected_vectors[point_id],
                ),
                "Final sparse verification failed",
            )

        require(
            client.count(
                collection_name=COLLECTION,
                exact=True,
            ).count == EXPECTED_POINTS,
            "Point count changed",
        )

        require(
            protected_counts(client) == protected_before,
            "Protected collection count changed",
        )

        result = {
            **plan,
            "complete": True,
            "updated_sparse_vectors": len(updates),
            "verified_sparse_vectors": len(after),
            "unchanged_dense_vectors": len(after),
            "unchanged_payloads": len(after),
            "point_count_after": EXPECTED_POINTS,
            "protected_collection_counts_after":
                protected_counts(client),
        }

        directory = (
            pilot.LOCAL / "day7_issue175_analysis"
        )

        directory.mkdir(parents=True, exist_ok=True)

        destination = directory / (
            f"bm25-repair-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
        )

        destination.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        print("\n===== BM25 REPAIR RESULT =====")
        print(json.dumps(result, indent=2))

        print("RESULT FILE:", destination)
        print("SUCCESS: BM25 vector repair completed.")


if __name__ == "__main__":
    main()
