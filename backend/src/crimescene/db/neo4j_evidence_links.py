"""CASE-001 증거 보유자 관계 적재."""

import argparse
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.settings import settings

CASE_ID = "CASE-001"

ALLOWED_HOLDER_TYPES = {
    "Person",
    "Place",
    "Object",
    "Organization",
}

LINK_QUERY = """
UNWIND $rows AS row

MATCH (e:CaseEntity {
    case_id: $case_id,
    entity_id: row.evidence_id
})
WHERE e.entity_type = 'Evidence'

MATCH (h:CaseEntity {
    case_id: $case_id,
    entity_id: row.holder_id
})

MERGE (e)-[r:EVIDENCE_HOLDER {
    case_id: $case_id,
    evidence_id: row.evidence_id
}]->(h)

SET
    r.access_scope = 'collected_evidence',
    r.source = 'evidence_rules.holder'

RETURN count(r) AS linked_count
"""


def prepare_evidence_links(rules, registry):
    """원본 증거 규칙에서 확인 가능한 연결만 생성한다."""

    expected_ids = {f"E{i:02d}" for i in range(1, 11)}

    if set(rules) != expected_ids:
        raise ValueError("증거 ID가 E01~E10과 일치하지 않습니다.")

    entities = {}

    for entity in registry:
        entity_id = entity["entity_id"]

        if entity["case_id"] != CASE_ID:
            raise ValueError("엔티티 사건 ID 불일치")

        if entity_id in entities:
            raise ValueError(f"중복 엔티티 ID: {entity_id}")

        entities[entity_id] = entity["type"]

    rows = []
    unresolved = []

    for evidence_id, rule in sorted(rules.items()):
        holder_id = rule.holder.strip()

        holder_type = entities.get(holder_id)

        if holder_type not in ALLOWED_HOLDER_TYPES:
            unresolved.append((evidence_id, holder_id))
            continue

        rows.append(
            {
                "evidence_id": evidence_id,
                "holder_id": holder_id,
            }
        )

    return rows, unresolved


def _write_links(tx, rows):
    """검증된 관계를 단일 트랜잭션으로 적재한다."""

    record = tx.run(
        LINK_QUERY,
        rows=rows,
        case_id=CASE_ID,
    ).single()

    if record is None:
        raise ValueError("관계 적재 결과가 없습니다.")

    linked_count = record["linked_count"]

    if linked_count != len(rows):
        raise ValueError("증거 관계 적재 개수가 일치하지 않습니다.")

    return linked_count


def ingest_evidence_links(driver, rows):
    """증거 관계를 중복 없이 적재한다."""

    if not rows:
        return 0

    with driver.session() as session:
        return session.execute_write(
            _write_links,
            rows,
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--rules",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 Neo4j에 관계를 적재한다.",
    )

    args = parser.parse_args()

    registry = load_entity_registry(args.registry)
    rules = load_evidence_rules(args.rules)

    rows, unresolved = prepare_evidence_links(
        rules,
        registry,
    )

    print(f"연결 가능한 증거: {len(rows)}개")
    print(f"연결 대상 미확인: {len(unresolved)}개")

    for evidence_id, holder in unresolved:
        print(f"미연결: {evidence_id} / holder={holder}")

    if not args.apply:
        print("검증만 완료했습니다. --apply로 적재하세요.")
        return

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
    )

    try:
        driver.verify_connectivity()

        count = ingest_evidence_links(
            driver,
            rows,
        )

    finally:
        driver.close()

    print(f"증거 관계 적재 완료: {count}개")


if __name__ == "__main__":
    main()
