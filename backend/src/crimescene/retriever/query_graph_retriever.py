"""자연어 질문 기반 CASE-001 Neo4j Graph Retrieval."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from neo4j import Driver

from crimescene.retriever.graph_evidence_search import (
    EvidenceGraphResult,
)
from crimescene.retriever.graph_retriever import (
    retrieve_character_graph,
)
from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    GraphSearchResult,
)
from crimescene.retriever.query_entity_extractor import (
    InaccessibleEntityMentionError,
    extract_question_entities,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import (
    RelationshipSourceEdge,
)

CASE_ID = "CASE-001"


@dataclass(frozen=True, slots=True)
class QuestionGraphContext:
    """질문에 연관된 접근 허용 그래프 검색 결과."""

    character_id: str
    matched_entity_ids: tuple[str, ...]
    relations: tuple[GraphSearchResult, ...]
    evidence: tuple[EvidenceGraphResult, ...]


def _validate_limit(value: int, name: str) -> None:
    """검색 제한값 검증."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}은 1~100 사이의 정수여야 합니다.")

    if not 1 <= value <= 100:
        raise ValueError(f"{name}은 1~100 사이여야 합니다.")


def _empty_context(
    character_id: str,
) -> QuestionGraphContext:
    """검색할 수 있는 관계가 없을 때 반환한다."""

    return QuestionGraphContext(
        character_id=character_id,
        matched_entity_ids=(),
        relations=(),
        evidence=(),
    )


def retrieve_question_graph(
    query: str,
    *,
    driver: Driver,
    active_character_id: str,
    state: GameState,
    registry: Sequence[Mapping[str, object]],
    trusted_edges: list[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    allowed_entity_ids: Iterable[str] = (),
    relation_top_k: int = 20,
    evidence_top_k: int = 10,
) -> QuestionGraphContext:
    """플레이어 질문과 관련된 Graph RAG 정보를 검색한다.

    검색 과정
    ---------
    1. 입력값 검증
    2. 현재 대화 NPC 해금 여부 확인
    3. 질문에서 엔티티 추출
    4. 접근 불가능한 엔티티 언급 여부 검증
    5. 기존 Graph Retriever로 접근 허용 관계 검색
    6. 질문 관련 관계 필터링
    7. 최종 검색 결과 반환

    Security
    --------
    - 현재 대화 NPC는 서버에서 결정한다.
    - 잠긴 NPC는 DB 검색 전에 차단한다.
    - 미수집 증거를 언급한 질문도 차단한다.
    - Neo4j 검색 결과는 기존 Graph Retriever에서 검증한다.
    - 관리자 전용 관계는 trusted_edges에 포함하지 않는다.
    - 원본 문서 본문을 반환하지 않는다.
    """

    # --------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------

    if not isinstance(query, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    if not query.strip():
        raise ValueError("유효한 질문이 필요합니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if (
        not isinstance(active_character_id, str)
        or active_character_id not in CHARACTER_IDS
    ):
        raise ValueError("유효하지 않은 NPC ID입니다.")

    _validate_limit(
        relation_top_k,
        "relation_top_k",
    )

    _validate_limit(
        evidence_top_k,
        "evidence_top_k",
    )

    # --------------------------------------------------
    # 2. 현재 대화 NPC 해금 상태 확인
    # --------------------------------------------------

    if active_character_id not in state.unlocked_characters:
        # 잠긴 NPC는 Neo4j에 연결하지 않는다.
        return _empty_context(active_character_id)

    # --------------------------------------------------
    # 3. 질문에서 엔티티 추출
    # --------------------------------------------------

    try:
        entities = extract_question_entities(
            query,
            registry=registry,
            state=state,
            evidence_rules=evidence_rules,
            allowed_entity_ids=allowed_entity_ids,
            # 접근 불가능한 엔티티 언급 시
            # 일반 관계 검색으로 대체하지 않음
            reject_inaccessible_mentions=True,
        )

    except InaccessibleEntityMentionError:
        # 미해금 NPC 또는 미수집 증거가
        # 질문에 등장하면 검색 자체를 차단
        return _empty_context(active_character_id)

    # --------------------------------------------------
    # 4. 질문 엔티티 ID 정리
    # --------------------------------------------------

    matched_ids = tuple(entity.entity_id for entity in entities)

    # 현재 대화 중인 NPC는 검색 대상에서 제외
    target_ids = set(matched_ids) - {active_character_id}

    # --------------------------------------------------
    # 5. Neo4j Graph Retrieval
    # --------------------------------------------------

    # 기존 접근 제어 기능을 그대로 재사용
    graph = retrieve_character_graph(
        driver,
        active_character_id,
        state,
        trusted_edges,
        evidence_rules,
        relation_top_k=relation_top_k,
        evidence_top_k=evidence_top_k,
    )

    # --------------------------------------------------
    # 6. 질문 관련 관계 필터링
    # --------------------------------------------------

    if target_ids:
        # 질문에 언급된 대상과 연결된 관계만 반환
        relations = tuple(
            relation
            for relation in graph.relations
            if relation.neighbor_id in target_ids
        )

        # 질문에 언급된 증거와 관련된 검색 결과만 반환
        evidence = tuple(
            item for item in graph.evidence if item.evidence_id in target_ids
        )

    else:
        # 특정 대상이 없는 일반 질문
        # 기존 접근 허용 그래프를 그대로 사용
        relations = graph.relations
        evidence = graph.evidence

    # --------------------------------------------------
    # 7. 최종 결과 반환
    # --------------------------------------------------

    return QuestionGraphContext(
        character_id=active_character_id,
        matched_entity_ids=matched_ids,
        relations=relations,
        evidence=evidence,
    )
