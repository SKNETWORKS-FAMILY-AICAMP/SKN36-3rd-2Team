"""CASE-001 증거 노드 Neo4j 적재."""

import argparse
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)
from crimescene.settings import settings

CASE_ID = "CASE-001"

EXPECTED_EVIDENCE_IDS = {f"E{i:02d}" for i in range(1, 11)}


CHECK_EXISTING_QUERY = """
MATCH (n:CaseEntity {case_id: $case_id})
WHERE n.entity_id IN $evidence_ids
  AND (
      n.entity_type IS NULL
      OR n.entity_type <> 'Evidence'
  )
RETURN n.entity_id AS entity_id
"""


EVIDENCE_NODE_QUERY = """
UNWIND $evidence_ids AS evidence_id

MERGE (n:CaseEntity {
    case_id: $case_id,
    entity_id: evidence_id
})

ON CREATE SET
    n.entity_type = 'Evidence',
    n.label = evidence_id

SET n:Evidence
"""


def ingest_evidence_nodes(
    driver,
    evidence_ids: set[str],
    *,
    case_id: str = CASE_ID,
) -> int:
    """E01~E10 증거 노드를 중복 없이 적재한다."""

    if evidence_ids != EXPECTED_EVIDENCE_IDS:
        raise ValueError("CASE-001 증거 목록이 E01~E10과 일치하지 않습니다.")

    ids = sorted(evidence_ids)

    def write_evidence(tx):
        # 기존 엔티티와 유형 충돌 확인
        conflicts = tx.run(
            CHECK_EXISTING_QUERY,
            case_id=case_id,
            evidence_ids=ids,
        ).data()

        if conflicts:
            raise ValueError(f"기존 엔티티 유형 충돌: {conflicts}")

        # 기존 E03은 유지하고 없는 노드만 생성
        tx.run(
            EVIDENCE_NODE_QUERY,
            case_id=case_id,
            evidence_ids=ids,
        ).consume()

    with driver.session() as session:
        session.execute_write(write_evidence)

    return len(ids)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--rules",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    rules = load_evidence_rules(args.rules)

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
    )

    try:
        driver.verify_connectivity()

        count = ingest_evidence_nodes(
            driver,
            set(rules),
        )

    finally:
        driver.close()

    print(f"증거 노드 적재 완료: {count}개")


if __name__ == "__main__":
    main()
