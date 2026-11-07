"""CASE-001 Neo4j 그래프 변경사항 적용."""

import argparse
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.db.neo4j_sync import (
    AREAS,
    QUERIES,
    build_expected_snapshot,
    build_sync_plan,
    find_source,
    read_database_snapshot,
)
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.loaders.relationship_loader import (
    load_relationship_edges,
)
from crimescene.scenario.source_timeline import load_source_timeline
from crimescene.settings import settings

CASE_ID = "CASE-001"

NODE_LABELS = ("Person", "Place", "Event", "Evidence")


def _read_snapshot_tx(tx):
    """현재 트랜잭션에서 그래프 상태를 읽는다."""

    snapshot = {area: {} for area in AREAS}

    for area, query in QUERIES.items():
        for row in tx.run(query, case_id=CASE_ID).data():
            key = row["key"]

            if not isinstance(key, str) or not key:
                raise ValueError(f"잘못된 그래프 식별자: {area}")

            if key in snapshot[area]:
                raise ValueError(f"중복 그래프 식별자: {area}/{key}")

            props = dict(row["props"] or {})

            if area == "relationships":
                props["source_id"] = row["source_id"]
                props["target_id"] = row["target_id"]

            snapshot[area][key] = props

    return snapshot


def _run_ids(tx, query, ids):
    """대상이 있을 때만 삭제 쿼리를 실행한다."""

    if ids:
        tx.run(
            query,
            case_id=CASE_ID,
            ids=list(ids),
        ).consume()


def _run_rows(tx, query, rows):
    """대상이 있을 때만 적재 쿼리를 실행한다."""

    if rows:
        tx.run(
            query,
            case_id=CASE_ID,
            rows=rows,
        ).consume()


def _selected_rows(expected, delta):
    """추가 또는 수정할 원본 레코드를 반환한다."""

    ids = sorted(set(delta.added) | set(delta.updated))

    return [{"id": record_id, **expected[record_id]} for record_id in ids]


def _sync_transaction(tx, expected, allow_delete):
    """하나의 Neo4j 트랜잭션으로 동기화를 수행한다."""

    actual = _read_snapshot_tx(tx)
    plan = build_sync_plan(expected, actual)

    if plan.total_changes == 0:
        return plan

    # 삭제는 명시적으로 승인된 경우에만 허용
    deleted_count = sum(len(delta.deleted) for delta in plan.areas.values())

    if deleted_count and not allow_delete:
        raise ValueError(
            f"삭제 대상 {deleted_count}건이 있습니다. --allow-delete 옵션이 필요합니다."
        )

    # 엔티티 유형 변경은 기존 Neo4j 라벨과 충돌할 수 있으므로
    # 별도의 스키마 마이그레이션으로 처리한다.
    for entity_id in plan.areas["entities"].updated:
        old_type = actual["entities"][entity_id].get("entity_type")
        new_type = expected["entities"][entity_id]["entity_type"]

        if old_type != new_type:
            raise ValueError(
                f"엔티티 유형 변경은 수동 마이그레이션이 필요합니다: {entity_id}"
            )

    # --------------------------------------------------------
    # 1. 오래된 관계 제거
    # --------------------------------------------------------

    _run_ids(
        tx,
        """
        MATCH (e:AdminEvent {case_id: $case_id})
              -[r:ADMIN_MENTIONS]->
              (n:AdminEntity {case_id: $case_id})
        WHERE e.event_id + '::' + n.entity_id IN $ids
        DELETE r
        """,
        plan.areas["admin_mentions"].deleted,
    )

    holder_delta = plan.areas["evidence_holders"]

    _run_ids(
        tx,
        """
        MATCH ()-[r:EVIDENCE_HOLDER {
            case_id: $case_id
        }]->()
        WHERE r.evidence_id IN $ids
        DELETE r
        """,
        (*holder_delta.deleted, *holder_delta.updated),
    )

    relation_delta = plan.areas["relationships"]

    _run_ids(
        tx,
        """
        MATCH ()-[r:CASE_RELATION {
            case_id: $case_id
        }]->()
        WHERE r.edge_id IN $ids
        DELETE r
        """,
        (*relation_delta.deleted, *relation_delta.updated),
    )

    # --------------------------------------------------------
    # 2. 원본에서 삭제된 노드 제거
    # --------------------------------------------------------

    # DETACH DELETE를 사용하지 않는다.
    # 예상하지 못한 관계가 남아 있다면 DELETE 실패로
    # 전체 트랜잭션을 롤백하기 위함이다.

    _run_ids(
        tx,
        """
        MATCH (n:AdminEvent {case_id: $case_id})
        WHERE n.event_id IN $ids
        DELETE n
        """,
        plan.areas["admin_events"].deleted,
    )

    _run_ids(
        tx,
        """
        MATCH (n:AdminEntity {case_id: $case_id})
        WHERE n.entity_id IN $ids
        DELETE n
        """,
        plan.areas["admin_entities"].deleted,
    )

    _run_ids(
        tx,
        """
        MATCH (n:CaseEntity {case_id: $case_id})
        WHERE n.entity_id IN $ids
        DELETE n
        """,
        plan.areas["entities"].deleted,
    )

    # --------------------------------------------------------
    # 3. 일반 엔티티 추가 및 수정
    # --------------------------------------------------------

    entity_rows = _selected_rows(
        expected["entities"],
        plan.areas["entities"],
    )

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MERGE (n:CaseEntity {
            case_id: $case_id,
            entity_id: row.entity_id
        })

        SET
            n.entity_type = row.entity_type,
            n.label = row.label
        """,
        entity_rows,
    )

    # 등록된 유형의 라벨만 적용
    for node_type in NODE_LABELS:
        typed_ids = [
            row["entity_id"] for row in entity_rows if row["entity_type"] == node_type
        ]

        if typed_ids:
            tx.run(
                f"""
                MATCH (n:CaseEntity {{
                    case_id: $case_id
                }})
                WHERE n.entity_id IN $ids
                SET n:{node_type}
                """,
                case_id=CASE_ID,
                ids=typed_ids,
            ).consume()

    # --------------------------------------------------------
    # 4. 관리자 사건 및 인물 추가·수정
    # --------------------------------------------------------

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MERGE (e:AdminEvent {
            case_id: $case_id,
            event_id: row.event_id
        })

        SET e += row
        """,
        _selected_rows(
            expected["admin_events"],
            plan.areas["admin_events"],
        ),
    )

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MERGE (n:AdminEntity {
            case_id: $case_id,
            entity_id: row.id
        })

        SET n.entity_type = row.entity_type
        """,
        _selected_rows(
            expected["admin_entities"],
            plan.areas["admin_entities"],
        ),
    )

    # --------------------------------------------------------
    # 5. 기존 사건 관계 추가·수정
    # --------------------------------------------------------

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MATCH (s:CaseEntity {
            case_id: $case_id,
            entity_id: row.source_id
        })

        MATCH (t:CaseEntity {
            case_id: $case_id,
            entity_id: row.target_id
        })

        MERGE (s)-[r:CASE_RELATION {
            case_id: $case_id,
            edge_id: row.edge_id
        }]->(t)

        SET r += row

        SET
            r.valid_from = date(row.valid_from),
            r.valid_to = date(row.valid_to)
        """,
        _selected_rows(
            expected["relationships"],
            plan.areas["relationships"],
        ),
    )

    # --------------------------------------------------------
    # 6. 증거 보유자 관계 추가·수정
    # --------------------------------------------------------

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MATCH (e:CaseEntity {
            case_id: $case_id,
            entity_id: row.evidence_id
        })

        MATCH (h:CaseEntity {
            case_id: $case_id,
            entity_id: row.holder_id
        })

        MERGE (e)-[r:EVIDENCE_HOLDER {
            case_id: $case_id,
            evidence_id: row.evidence_id
        }]->(h)

        SET
            r.access_scope = row.access_scope,
            r.source = row.source
        """,
        _selected_rows(
            expected["evidence_holders"],
            plan.areas["evidence_holders"],
        ),
    )

    # --------------------------------------------------------
    # 7. 관리자 사건 인물 참조 추가
    # --------------------------------------------------------

    mention_rows = []

    for key in plan.areas["admin_mentions"].added:
        event_id, separator, entity_id = key.partition("::")

        if not separator or not event_id or not entity_id:
            raise ValueError(f"잘못된 관리자 참조 ID: {key}")

        mention_rows.append(
            {
                "event_id": event_id,
                "entity_id": entity_id,
            }
        )

    _run_rows(
        tx,
        """
        UNWIND $rows AS row

        MATCH (e:AdminEvent {
            case_id: $case_id,
            event_id: row.event_id
        })

        MATCH (n:AdminEntity {
            case_id: $case_id,
            entity_id: row.entity_id
        })

        MERGE (e)-[:ADMIN_MENTIONS]->(n)
        """,
        mention_rows,
    )

    # --------------------------------------------------------
    # 8. 트랜잭션 커밋 전 최종 무결성 검증
    # --------------------------------------------------------

    verified = _read_snapshot_tx(tx)
    remaining = build_sync_plan(expected, verified)

    if remaining.total_changes:
        raise RuntimeError(
            f"Neo4j 동기화 후 불일치 {remaining.total_changes}건이 남아 있습니다."
        )

    return plan


def apply_neo4j_snapshot(
    driver,
    expected,
    *,
    allow_delete=False,
):
    """검증된 CASE-001 원본 스냅샷을 적용한다."""

    if settings.app_env.lower() != "development":
        raise RuntimeError(
            "관리자 사건 데이터 동기화는 로컬 개발 환경에서만 허용됩니다."
        )

    if not isinstance(allow_delete, bool):
        raise TypeError("allow_delete는 bool이어야 합니다.")

    with driver.session() as session:
        return session.execute_write(
            _sync_transaction,
            expected,
            allow_delete,
        )


def main():
    parser = argparse.ArgumentParser(description="CASE-001 Neo4j synchronization")

    parser.add_argument(
        "--root",
        type=Path,
        default=Path("../.local/case001_v7_1"),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--allow-delete",
        action="store_true",
    )

    args = parser.parse_args()

    root = args.root.resolve()

    if not root.is_dir():
        raise FileNotFoundError(root)

    entities = load_entity_registry(find_source(root, "entity_registry.json"))

    relationships = load_relationship_edges(
        find_source(root, "relationship_edges_source.json")
    )

    evidence_rules = load_evidence_rules(find_source(root, "evidence_rules.json"))

    events = load_source_timeline(find_source(root, "timeline_events.json"))

    expected = build_expected_snapshot(
        entities,
        relationships,
        evidence_rules,
        events,
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

        if args.apply:
            plan = apply_neo4j_snapshot(
                driver,
                expected,
                allow_delete=args.allow_delete,
            )
        else:
            actual = read_database_snapshot(driver)
            plan = build_sync_plan(expected, actual)

    finally:
        driver.close()

    print("=" * 55)
    print("CASE-001 NEO4J SYNC")
    print("=" * 55)

    for area, delta in plan.areas.items():
        print(
            f"{area}: "
            f"add={len(delta.added)}, "
            f"update={len(delta.updated)}, "
            f"delete={len(delta.deleted)}"
        )

    print(f"TOTAL CHANGES: {plan.total_changes}")

    if args.apply:
        print("SYNC APPLIED")
    else:
        print("DRY RUN ONLY - NO DATABASE CHANGES")


if __name__ == "__main__":
    main()
