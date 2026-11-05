from unittest.mock import MagicMock

import pytest

from crimescene.db import connections


def test_qdrant_connection_success(monkeypatch):
    """Qdrant 연결 성공 테스트."""

    mock_client = MagicMock()
    mock_factory = MagicMock(return_value=mock_client)

    monkeypatch.setattr(
        connections,
        "QdrantClient",
        mock_factory,
    )

    connections.check_qdrant_connection()

    mock_factory.assert_called_once_with(
        url=connections.settings.qdrant_url,
        timeout=5,
    )

    mock_client.get_collections.assert_called_once()
    mock_client.close.assert_called_once()


def test_qdrant_connection_failure(monkeypatch):
    """Qdrant 연결 실패 시 예외 및 리소스 정리 테스트."""

    mock_client = MagicMock()
    mock_client.get_collections.side_effect = RuntimeError("Qdrant connection failed")

    monkeypatch.setattr(
        connections,
        "QdrantClient",
        MagicMock(return_value=mock_client),
    )

    with pytest.raises(RuntimeError, match="Qdrant connection failed"):
        connections.check_qdrant_connection()

    mock_client.close.assert_called_once()


def test_neo4j_connection_success(monkeypatch):
    """Neo4j 연결 성공 테스트."""

    mock_driver = MagicMock()
    mock_driver.__enter__.return_value = mock_driver

    mock_factory = MagicMock(return_value=mock_driver)

    monkeypatch.setattr(
        connections.GraphDatabase,
        "driver",
        mock_factory,
    )

    connections.check_neo4j_connection()

    mock_factory.assert_called_once_with(
        connections.settings.neo4j_uri,
        auth=(
            connections.settings.neo4j_user,
            connections.settings.neo4j_password.get_secret_value(),
        ),
        connection_timeout=5,
    )

    mock_driver.verify_connectivity.assert_called_once()
    mock_driver.__exit__.assert_called_once()


def test_neo4j_connection_failure(monkeypatch):
    """Neo4j 연결 실패 시 예외 처리 테스트."""

    mock_driver = MagicMock()
    mock_driver.__enter__.return_value = mock_driver

    mock_driver.verify_connectivity.side_effect = RuntimeError(
        "Neo4j connection failed"
    )

    monkeypatch.setattr(
        connections.GraphDatabase,
        "driver",
        MagicMock(return_value=mock_driver),
    )

    with pytest.raises(RuntimeError, match="Neo4j connection failed"):
        connections.check_neo4j_connection()

    mock_driver.__exit__.assert_called_once()
