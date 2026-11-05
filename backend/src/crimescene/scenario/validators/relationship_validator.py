from collections.abc import Mapping, Sequence

from crimescene.scenario.integrity import IntegrityViolation
from crimescene.scenario.schemas.character import CharacterProfile
from crimescene.scenario.schemas.relationship import (
    HiddenRelationshipEdge,
    RelationshipSourceEdge,
)


def validate_character_relationship_references(
    characters: Sequence[CharacterProfile],
    edges: Sequence[RelationshipSourceEdge],
    hidden_edges: Sequence[HiddenRelationshipEdge],
    entity_registry: Sequence[Mapping[str, str]],
    *,
    case_id: str,
) -> list[IntegrityViolation]:
    """NPC 및 관계 데이터의 엔티티 참조 무결성을 검증한다."""

    errors: list[IntegrityViolation] = []

    def add_error(path: str, message: str) -> None:
        errors.append(
            IntegrityViolation(
                path=path,
                message=message,
            )
        )

    # 1. 엔티티 등록 정보 검증
    entities: dict[str, Mapping[str, str]] = {}

    for index, entity in enumerate(entity_registry):
        entity_id = entity.get("entity_id")

        if not entity_id:
            add_error(
                f"entity_registry[{index}].entity_id",
                "엔티티 ID가 없습니다.",
            )
            continue

        if entity_id in entities:
            add_error(
                f"entity_registry[{index}].entity_id",
                f"중복된 엔티티 ID: {entity_id}",
            )

        entities[entity_id] = entity

        if entity.get("case_id") != case_id:
            add_error(
                f"entity_registry[{index}].case_id",
                "사건 ID가 일치하지 않습니다.",
            )

    # 2. NPC 프로필과 등록 정보 비교
    for index, character in enumerate(characters):
        entity = entities.get(character.id)

        if entity is None:
            add_error(
                f"characters[{index}].id",
                f"등록되지 않은 NPC: {character.id}",
            )
            continue

        if entity.get("type") != "Person":
            add_error(
                f"characters[{index}].id",
                "NPC의 엔티티 유형이 Person이 아닙니다.",
            )

        if entity.get("label") != character.name:
            add_error(
                f"characters[{index}].name",
                f"NPC 이름 불일치: {character.id}",
            )

    # 3. 일반 관계 검증
    for index, edge in enumerate(edges):
        if edge.case_id != case_id:
            add_error(
                f"edges[{index}].case_id",
                "관계의 사건 ID가 일치하지 않습니다.",
            )

        for field in ("source_id", "target_id"):
            entity_id = getattr(edge, field)

            if entity_id not in entities:
                add_error(
                    f"edges[{index}].{field}",
                    f"등록되지 않은 엔티티: {entity_id}",
                )

        # 관계를 주장한 인물 검증
        for speaker_index, speaker_id in enumerate(edge.asserted_by):
            entity = entities.get(speaker_id)

            if entity is None or entity.get("type") != "Person":
                add_error(
                    f"edges[{index}].asserted_by[{speaker_index}]",
                    f"등록되지 않은 인물: {speaker_id}",
                )

    # 4. 관리자 비밀 관계 검증
    for index, edge in enumerate(hidden_edges):
        for field in ("source_id", "target_id"):
            entity_id = getattr(edge, field)

            if entity_id not in entities:
                add_error(
                    f"hidden_edges[{index}].{field}",
                    f"등록되지 않은 엔티티: {entity_id}",
                )

    return errors
