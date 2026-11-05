from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from crimescene.settings import settings


def check_qdrant_connection() -> None:
    """Qdrant 서버 연결 상태를 확인합니다."""

    client = QdrantClient(
        url=settings.qdrant_url,
        timeout=5,
    )

    try:
        client.get_collections()
    finally:
        client.close()


def check_neo4j_connection() -> None:
    """Neo4j 서버 연결 상태를 확인합니다."""

    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
        connection_timeout=5,
    ) as driver:
        driver.verify_connectivity()


if __name__ == "__main__":
    check_qdrant_connection()
    print("✅ Qdrant 연결 성공")

    check_neo4j_connection()
    print("✅ Neo4j 연결 성공")
