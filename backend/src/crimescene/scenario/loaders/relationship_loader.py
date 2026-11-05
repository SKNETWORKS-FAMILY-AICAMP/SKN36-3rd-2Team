from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from crimescene.scenario.schemas.relationship import (
    HiddenRelationshipEdge,
    RelationshipSourceEdge,
)

# Pydantic JSON 배열 검증기
_relationship_adapter = TypeAdapter(list[RelationshipSourceEdge])

_hidden_adapter = TypeAdapter(list[HiddenRelationshipEdge])


def load_relationship_edges(
    file_path: Path,
) -> list[RelationshipSourceEdge]:
    """v7.1 일반 관계 데이터를 읽고 검증한다."""

    # 1. JSON 파일 읽기
    content = file_path.read_text(encoding="utf-8-sig")

    # 2. Pydantic 스키마 검증
    edges = _relationship_adapter.validate_json(content)

    if not edges:
        raise ValueError("관계 데이터가 비어 있습니다.")

    # 3. 관계 ID 중복 검사
    edge_ids = [edge.edge_id for edge in edges]

    duplicates = [edge_id for edge_id, count in Counter(edge_ids).items() if count > 1]

    if duplicates:
        raise ValueError(f"중복된 관계 ID가 존재합니다: {duplicates}")

    return edges


def load_hidden_relationship_edges(
    file_path: Path,
) -> list[HiddenRelationshipEdge]:
    """v7.1 관리자 전용 비밀 관계를 읽고 검증한다.

    반환 데이터는 NPC 프롬프트나 일반 RAG에 전달하면 안 된다.
    """

    # 1. JSON 파일 읽기
    content = file_path.read_text(encoding="utf-8-sig")

    # 2. 관리자 비밀 관계 스키마 검증
    edges = _hidden_adapter.validate_json(content)

    if not edges:
        raise ValueError("관리자 비밀 관계 데이터가 비어 있습니다.")

    # 3. 동일한 비밀 관계 중복 검사
    relationship_keys = [
        (
            edge.source_id,
            edge.relation,
            edge.target_id,
            edge.year,
        )
        for edge in edges
    ]

    duplicates = [key for key, count in Counter(relationship_keys).items() if count > 1]

    if duplicates:
        raise ValueError(f"중복된 관리자 비밀 관계가 존재합니다: {duplicates}")

    return edges
