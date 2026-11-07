"""CASE-001 인물 관계 및 증거 통합 Graph Retriever."""

from collections.abc import Mapping
from dataclasses import dataclass

from neo4j import Driver

from crimescene.retriever.graph_evidence_search import (
    EvidenceGraphResult,
    search_character_evidence,
)
from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    GraphSearchResult,
    search_character_relations,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"


@dataclass(frozen=True)
class CharacterGraphContext:
    """접근 권한 검증이 완료된 인물 그래프 검색 결과."""

    character_id: str
    relations: tuple[GraphSearchResult, ...]
    evidence: tuple[EvidenceGraphResult, ...]


def _validate_limit(value: int, name: str) -> None:
    """검색 개수 제한값을 검증한다."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}은 정수여야 합니다.")

    if not 1 <= value <= 100:
        raise ValueError(f"{name}은 1~100 사이여야 합니다.")


def retrieve_character_graph(
    driver: Driver,
    character_id: str,
    state: GameState,
    trusted_edges: list[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    *,
    relation_top_k: int = 20,
    evidence_top_k: int = 10,
) -> CharacterGraphContext:
    """게임 상태에 따라 접근 가능한 인물 관계와 증거를 검색한다.

    trusted_edges와 evidence_rules는 서버에서 검증된 원본만 사용한다.
    관리자 전용 사건 그래프는 조회하지 않는다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    _validate_limit(relation_top_k, "relation_top_k")
    _validate_limit(evidence_top_k, "evidence_top_k")

    # 미해금 인물은 DB 조회 없이 종료
    if character_id not in state.unlocked_characters:
        return CharacterGraphContext(
            character_id=character_id,
            relations=(),
            evidence=(),
        )

    # 1. 접근 가능한 인물 관계 검색
    relations = search_character_relations(
        driver,
        character_id,
        state,
        trusted_edges,
        top_k=relation_top_k,
    )

    # 2. 수집 완료된 증거 관계 검색
    evidence = search_character_evidence(
        driver,
        character_id,
        state,
        evidence_rules,
        top_k=evidence_top_k,
    )

    return CharacterGraphContext(
        character_id=character_id,
        relations=tuple(relations),
        evidence=tuple(evidence),
    )
