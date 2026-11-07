from unittest.mock import MagicMock

import pytest

from crimescene.db.neo4j_ingest import (
    ingest_case_graph,
    validate_graph_data,
)
from crimescene.scenario.schemas.relationship import (
    RelationshipSourceEdge,
)


@pytest.fixture
def sample_data():
    entities = [
        {
            "entity_id": "C01",
            "type": "Person",
            "label": "인물 A",
            "case_id": "CASE-001",
        },
        {
            "entity_id": "C02",
            "type": "Person",
            "label": "인물 B",
            "case_id": "CASE-001",
        },
    ]

    edge = RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "C02",
            "relation": "KNOWS",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": "documented",
            "source_doc_ids": [],
            "asserted_by": [],
            "access_scope": "public",
            "required_evidence": [],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )

    return entities, [edge]


def test_valid_graph_data(sample_data):
    """정상 그래프 데이터 검증."""

    entities, edges = sample_data

    validate_graph_data(entities, edges)


def test_duplicate_entity(sample_data):
    """중복 엔티티 차단."""

    entities, edges = sample_data

    entities.append(entities[0].copy())

    with pytest.raises(ValueError, match="중복 엔티티"):
        validate_graph_data(entities, edges)


def test_unknown_relationship_entity(sample_data):
    """존재하지 않는 엔티티 참조 차단."""

    entities, edges = sample_data

    invalid = edges[0].model_copy(update={"target_id": "UNKNOWN"})

    with pytest.raises(ValueError, match="존재하지 않는"):
        validate_graph_data(entities, [invalid])


def test_ingest_graph(sample_data):
    """Neo4j 적재 트랜잭션 호출 검증."""

    entities, edges = sample_data

    driver = MagicMock()

    result = ingest_case_graph(
        driver,
        entities,
        edges,
    )

    assert result == {
        "entities": 2,
        "relationships": 1,
    }

    session = driver.session.return_value.__enter__.return_value

    session.execute_write.assert_called_once()


def test_invalid_data_not_written(sample_data):
    """잘못된 데이터는 DB 적재 이전에 차단."""

    entities, edges = sample_data

    driver = MagicMock()

    with pytest.raises(ValueError):
        ingest_case_graph(
            driver,
            entities,
            [edges[0].model_copy(update={"source_id": "UNKNOWN"})],
        )

    driver.session.assert_not_called()
