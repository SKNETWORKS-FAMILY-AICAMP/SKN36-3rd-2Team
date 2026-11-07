"""CASE-001 Neo4j 그래프 스키마 관리."""

from neo4j import Driver

SCHEMA_QUERIES = [
    # 사건별 엔티티 중복 방지
    """
    CREATE CONSTRAINT case_entity_identity IF NOT EXISTS
    FOR (n:CaseEntity)
    REQUIRE (n.case_id, n.entity_id) IS UNIQUE
    """,
    # 사건별 관계 중복 방지
    """
    CREATE CONSTRAINT case_relationship_identity IF NOT EXISTS
    FOR ()-[r:CASE_RELATION]-()
    REQUIRE (r.case_id, r.edge_id) IS UNIQUE
    """,
    # 사건 및 엔티티 유형 검색 최적화
    """
    CREATE INDEX case_entity_type IF NOT EXISTS
    FOR (n:CaseEntity)
    ON (n.case_id, n.entity_type)
    """,
]


def ensure_graph_schema(driver: Driver) -> None:
    """Neo4j 그래프 제약조건 및 인덱스를 생성한다."""

    with driver.session() as session:
        for query in SCHEMA_QUERIES:
            session.run(query).consume()
