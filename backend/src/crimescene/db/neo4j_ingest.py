"""CASE-001 Neo4j 엔티티 및 관계 적재."""

import argparse
import json
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.db.neo4j_schema import ensure_graph_schema
from crimescene.scenario.loaders.relationship_loader import (
    load_relationship_edges,
)
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge
from crimescene.settings import settings

NODE_QUERY = """
UNWIND $rows AS row

MERGE (n:CaseEntity {
    case_id: row.case_id,
    entity_id: row.entity_id
})

SET
    n.label = row.label,
    n.entity_type = row.type
"""


RELATIONSHIP_QUERY = """
UNWIND $rows AS row

MATCH (source:CaseEntity {
    case_id: row.case_id,
    entity_id: row.source_id
})

MATCH (target:CaseEntity {
    case_id: row.case_id,
    entity_id: row.target_id
})

MERGE (source)-[r:CASE_RELATION {
    case_id: row.case_id,
    edge_id: row.edge_id
}]->(target)

SET r += row
SET
    r.valid_from = date(row.valid_from),
    r.valid_to = date(row.valid_to)
"""


NODE_TYPES = (
    "Person",
    "Place",
    "Event",
    "Evidence",
)


def load_entity_registry(path: Path) -> list[dict]:
    """엔티티 등록 정보를 읽는다."""

    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, list) or not data:
        raise ValueError("엔티티 목록이 비어 있거나 형식이 잘못됐습니다.")

    return data


def validate_graph_data(
    entities: list[dict],
    edges: list[RelationshipSourceEdge],
    *,
    case_id: str = "CASE-001",
) -> None:
    """Neo4j 적재 이전에 데이터 무결성을 검증한다."""

    if not entities:
        raise ValueError("적재할 엔티티가 없습니다.")

    if not edges:
        raise ValueError("적재할 관계가 없습니다.")

    entity_ids = set()

    for entity in entities:
        if not isinstance(entity, dict):
            raise TypeError("엔티티 형식이 올바르지 않습니다.")

        entity_id = entity.get("entity_id")

        for field in ("entity_id", "type", "label", "case_id"):
            value = entity.get(field)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"엔티티 필드 오류: {field}")

        if entity["case_id"] != case_id:
            raise ValueError("엔티티 사건 ID가 일치하지 않습니다.")

        if entity_id in entity_ids:
            raise ValueError(f"중복 엔티티 ID: {entity_id}")

        entity_ids.add(entity_id)

    edge_ids = set()

    for edge in edges:
        if not isinstance(edge, RelationshipSourceEdge):
            raise TypeError("검증되지 않은 관계 데이터입니다.")

        if edge.case_id != case_id:
            raise ValueError("관계 사건 ID가 일치하지 않습니다.")

        if edge.edge_id in edge_ids:
            raise ValueError(f"중복 관계 ID: {edge.edge_id}")

        edge_ids.add(edge.edge_id)

        if edge.source_id not in entity_ids:
            raise ValueError(f"존재하지 않는 시작 엔티티: {edge.source_id}")

        if edge.target_id not in entity_ids:
            raise ValueError(f"존재하지 않는 대상 엔티티: {edge.target_id}")

        if edge.access_scope not in {
            "public",
            "conditional",
            "ending_only",
        }:
            raise ValueError("허용되지 않은 관계 접근 등급입니다.")


def _write_graph(tx, entities, edge_rows, case_id):
    """노드와 관계를 하나의 트랜잭션으로 적재한다."""

    tx.run(
        NODE_QUERY,
        rows=entities,
    ).consume()

    # 등록된 유형에 따라 Neo4j 라벨을 추가한다.
    # 라벨은 서버 코드에 정의된 값만 사용한다.
    for node_type in NODE_TYPES:
        query = f"""
        MATCH (n:CaseEntity {{
            case_id: $case_id,
            entity_type: $node_type
        }})
        SET n:{node_type}
        """

        tx.run(
            query,
            case_id=case_id,
            node_type=node_type,
        ).consume()

    tx.run(
        RELATIONSHIP_QUERY,
        rows=edge_rows,
    ).consume()


def ingest_case_graph(
    driver,
    entities: list[dict],
    edges: list[RelationshipSourceEdge],
    *,
    case_id: str = "CASE-001",
) -> dict[str, int]:
    """검증된 CASE-001 데이터를 Neo4j에 적재한다."""

    # DB에 쓰기 전에 전체 데이터를 검증한다.
    validate_graph_data(
        entities,
        edges,
        case_id=case_id,
    )

    # 날짜를 포함한 원본 관계 속성을 보존한다.
    edge_rows = [edge.model_dump(mode="json") for edge in edges]

    with driver.session() as session:
        session.execute_write(
            _write_graph,
            entities,
            edge_rows,
            case_id,
        )

    return {
        "entities": len(entities),
        "relationships": len(edges),
    }


def main():
    parser = argparse.ArgumentParser(description="CASE-001 Neo4j 그래프 적재")

    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--relationships",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    entities = load_entity_registry(args.registry)

    edges = load_relationship_edges(args.relationships)

    # DB 연결 이전에 원본 데이터 검증
    validate_graph_data(
        entities,
        edges,
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

        ensure_graph_schema(driver)

        result = ingest_case_graph(
            driver,
            entities,
            edges,
        )

    finally:
        driver.close()

    print("Neo4j 데이터 적재 완료")
    print(f"엔티티: {result['entities']}개")
    print(f"관계: {result['relationships']}개")


if __name__ == "__main__":
    main()
