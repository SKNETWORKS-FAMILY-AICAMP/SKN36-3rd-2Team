"""CASE-001 관리자 전용 사건 타임라인 그래프 적재."""

import argparse
import json
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.scenario.source_timeline import (
    SourceTimelineEvent,
    load_source_timeline,
)
from crimescene.settings import settings

CASE_ID = "CASE-001"


SCHEMA_QUERIES = [
    """
    CREATE CONSTRAINT admin_event_identity IF NOT EXISTS
    FOR (e:AdminEvent)
    REQUIRE (e.case_id, e.event_id) IS UNIQUE
    """,
    """
    CREATE CONSTRAINT admin_entity_identity IF NOT EXISTS
    FOR (n:AdminEntity)
    REQUIRE (n.case_id, n.entity_id) IS UNIQUE
    """,
]


EVENT_QUERY = """
UNWIND $rows AS row

MERGE (e:AdminEvent {
    case_id: row.case_id,
    event_id: row.event_id
})

SET
    e.description = row.description,
    e.incident_year = row.incident_year,
    e.date_start = row.date_start,
    e.date_end = row.date_end,
    e.time_start = row.time_start,
    e.time_end = row.time_end,
    e.raw_time = row.raw_time,
    e.temporal_precision = row.temporal_precision,
    e.truth_status = row.truth_status,
    e.access_scope = 'admin_only'
"""


MENTION_QUERY = """
UNWIND $rows AS row

MATCH (e:AdminEvent {
    case_id: row.case_id,
    event_id: row.event_id
})

MERGE (n:AdminEntity {
    case_id: row.case_id,
    entity_id: row.entity_id
})

SET n.entity_type = row.entity_type

MERGE (e)-[:ADMIN_MENTIONS]->(n)
"""


def load_registry(path: Path) -> list[dict]:
    """엔티티 원본을 읽는다."""

    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, list) or not data:
        raise ValueError("엔티티 원본이 올바르지 않습니다.")

    return data


def build_admin_graph_rows(
    events: list[SourceTimelineEvent],
    registry: list[dict],
) -> tuple[list[dict], list[dict]]:
    """관리자 전용 사건 노드와 인물 참조 관계를 구성한다."""

    if not events:
        raise ValueError("사건 데이터가 비어 있습니다.")

    entity_types = {}

    for entity in registry:
        entity_id = entity.get("entity_id")
        entity_type = entity.get("type")

        if entity.get("case_id") != CASE_ID:
            raise ValueError("엔티티 사건 ID 불일치")

        if not isinstance(entity_id, str) or not entity_id:
            raise ValueError("유효하지 않은 엔티티 ID")

        if not isinstance(entity_type, str) or not entity_type:
            raise ValueError("유효하지 않은 엔티티 유형")

        if entity_id in entity_types:
            raise ValueError("중복 엔티티 ID")

        entity_types[entity_id] = entity_type

    event_rows = []
    mention_rows = []

    seen_events = set()

    for event in events:
        if not isinstance(event, SourceTimelineEvent):
            raise TypeError("검증되지 않은 사건 데이터입니다.")

        if event.case_id != CASE_ID:
            raise ValueError("사건 ID 불일치")

        if event.access_scope != "admin_only":
            raise ValueError("관리자 전용 사건만 허용합니다.")

        if event.event_id in seen_events:
            raise ValueError("중복 사건 ID")

        seen_events.add(event.event_id)

        event_rows.append(
            {
                "case_id": CASE_ID,
                "event_id": event.event_id,
                "description": event.event,
                "incident_year": event.incident_year,
                "date_start": (
                    event.date_start.isoformat() if event.date_start else None
                ),
                "date_end": (event.date_end.isoformat() if event.date_end else None),
                "time_start": (
                    event.time_start.isoformat() if event.time_start else None
                ),
                "time_end": (event.time_end.isoformat() if event.time_end else None),
                "raw_time": event.raw_time,
                "temporal_precision": event.temporal_precision,
                "truth_status": event.truth_status,
            }
        )

        # 중복 참조 제거
        for entity_id in sorted(set(event.named_entity_ids)):
            entity_type = entity_types.get(entity_id)

            if entity_type is None:
                raise ValueError(f"등록되지 않은 엔티티: {entity_id}")

            mention_rows.append(
                {
                    "case_id": CASE_ID,
                    "event_id": event.event_id,
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                }
            )

    return event_rows, mention_rows


def ensure_admin_schema(driver) -> None:
    """관리자 그래프 제약조건을 생성한다."""

    with driver.session() as session:
        for query in SCHEMA_QUERIES:
            session.run(query).consume()


def _write_admin_graph(tx, event_rows, mention_rows):
    """하나의 트랜잭션으로 사건 및 참조 관계를 적재한다."""

    tx.run(
        EVENT_QUERY,
        rows=event_rows,
    ).consume()

    tx.run(
        MENTION_QUERY,
        rows=mention_rows,
    ).consume()


def ingest_admin_timeline(
    driver,
    events: list[SourceTimelineEvent],
    registry: list[dict],
) -> dict[str, int]:
    """관리자 전용 타임라인을 적재한다."""

    event_rows, mention_rows = build_admin_graph_rows(
        events,
        registry,
    )

    ensure_admin_schema(driver)

    with driver.session() as session:
        session.execute_write(
            _write_admin_graph,
            event_rows,
            mention_rows,
        )

    return {
        "events": len(event_rows),
        "mentions": len(mention_rows),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--timeline",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    args = parser.parse_args()

    events = load_source_timeline(args.timeline)
    registry = load_registry(args.registry)

    event_rows, mention_rows = build_admin_graph_rows(
        events,
        registry,
    )

    print(f"Validated events: {len(event_rows)}")
    print(f"Validated references: {len(mention_rows)}")

    if not args.apply:
        print("Dry run completed. No database changes.")
        return

    # 공유 운영 DB에는 관리자 원본을 적재하지 않는다.
    if settings.app_env.lower() != "development":
        raise RuntimeError(
            "관리자 사건 그래프는 로컬 개발 환경에서만 적재할 수 있습니다."
        )

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
    )

    try:
        driver.verify_connectivity()

        result = ingest_admin_timeline(
            driver,
            events,
            registry,
        )

    finally:
        driver.close()

    print(f"Admin events ingested: {result['events']}")
    print(f"Admin references ingested: {result['mentions']}")


if __name__ == "__main__":
    main()
