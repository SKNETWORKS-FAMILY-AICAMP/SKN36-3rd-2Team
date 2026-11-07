from unittest.mock import MagicMock

import pytest

from crimescene.db.neo4j_schema import (
    SCHEMA_QUERIES,
    ensure_graph_schema,
)


def test_create_graph_schema():
    """그래프 스키마 생성 쿼리가 모두 실행되는지 검증."""

    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value

    ensure_graph_schema(driver)

    assert session.run.call_count == len(SCHEMA_QUERIES)

    executed_queries = [call.args[0] for call in session.run.call_args_list]

    assert "case_entity_identity" in executed_queries[0]
    assert "case_relationship_identity" in executed_queries[1]
    assert "case_entity_type" in executed_queries[2]


def test_schema_creation_failure():
    """Neo4j 오류 발생 시 예외를 전달하는지 검증."""

    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value

    session.run.side_effect = RuntimeError("Neo4j schema error")

    with pytest.raises(RuntimeError, match="Neo4j schema error"):
        ensure_graph_schema(driver)
