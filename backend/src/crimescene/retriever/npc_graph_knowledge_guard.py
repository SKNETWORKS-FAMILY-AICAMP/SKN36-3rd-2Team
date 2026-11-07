"""CASE-001 NPC별 Graph 지식 범위 검증."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from crimescene.retriever.graph_evidence_search import EvidenceGraphResult
from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    GraphSearchResult,
    is_relation_visible,
)
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"


@dataclass(frozen=True, slots=True)
class NPCGraphKnowledgeResult:
    """NPC 지식 검사를 통과한 Graph 및 통합 검색 후보."""

    candidates: tuple[FusedSearchCandidate, ...]
    graph_context: QuestionGraphContext


def _validate_ids(
    values: Iterable[str],
    name: str,
) -> set[str]:
    """서버에서 승인한 ID 목록을 검증한다."""

    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name}은 문자열 목록이어야 합니다.")

    result: set[str] = set()

    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{name}의 ID는 문자열이어야 합니다.")

        if not value.strip():
            raise ValueError(f"{name}에 유효하지 않은 ID가 있습니다.")

        result.add(value)

    return result


def restrict_npc_graph_knowledge(
    candidates: Sequence[FusedSearchCandidate],
    graph_context: QuestionGraphContext,
    *,
    state: GameState,
    active_character_id: str,
    trusted_edges: Sequence[RelationshipSourceEdge],
    evidence_rules: dict[str, EvidenceRule],
    known_relation_ids: Iterable[str] = (),
    known_evidence_ids: Iterable[str] = (),
) -> NPCGraphKnowledgeResult:
    """현재 NPC가 알 수 있는 Graph 근거만 남긴다.

    보안 원칙:
        - 미해금 NPC 접근 차단
        - NPC별 명시적 지식 허용 목록 적용
        - 원본 관계와 검색 결과 재검증
        - GameState 관계 공개 조건 재검증
        - 미수집 증거 차단
        - 승인되지 않은 Graph 근거 제거
        - 기본 접근 거부(Fail Closed)

    주의:
        허용 목록은 반드시 서버에서 검증한
        시나리오 정책으로 생성해야 한다.
    """

    # --------------------------------------------------
    # 1. 기본 입력값 검증
    # --------------------------------------------------

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(active_character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if active_character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if not isinstance(graph_context, QuestionGraphContext):
        raise TypeError("QuestionGraphContext가 필요합니다.")

    if graph_context.character_id != active_character_id:
        raise ValueError("Graph 검색 대상 NPC가 일치하지 않습니다.")

    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError("검색 후보는 시퀀스여야 합니다.")

    # --------------------------------------------------
    # 2. NPC별 허용 ID 검증
    # --------------------------------------------------

    relation_grants = _validate_ids(
        known_relation_ids,
        "허용 관계 ID",
    )

    evidence_grants = _validate_ids(
        known_evidence_ids,
        "허용 증거 ID",
    )

    empty_graph = QuestionGraphContext(
        character_id=active_character_id,
        matched_entity_ids=(),
        relations=(),
        evidence=(),
    )

    # --------------------------------------------------
    # 3. 미해금 NPC 차단
    # --------------------------------------------------

    if active_character_id not in state.unlocked_characters:
        return NPCGraphKnowledgeResult(
            candidates=(),
            graph_context=empty_graph,
        )

    # --------------------------------------------------
    # 4. 서버 원본 관계 색인
    # --------------------------------------------------

    trusted_by_id: dict[str, RelationshipSourceEdge] = {}

    for edge in trusted_edges:
        if not isinstance(edge, RelationshipSourceEdge):
            raise TypeError("검증되지 않은 관계 원본입니다.")

        if edge.case_id != state.case_id:
            raise ValueError("관계의 사건 ID가 일치하지 않습니다.")

        if edge.edge_id in trusted_by_id:
            raise ValueError("중복된 원본 관계 ID입니다.")

        trusted_by_id[edge.edge_id] = edge

    # --------------------------------------------------
    # 5. NPC 관계 허용 목록 검증
    # --------------------------------------------------

    for edge_id in relation_grants:
        edge = trusted_by_id.get(edge_id)

        if edge is None:
            raise ValueError("존재하지 않는 NPC 관계 허용 ID입니다.")

        if active_character_id not in {
            edge.source_id,
            edge.target_id,
        }:
            raise ValueError("현재 NPC와 무관한 관계 허용 ID입니다.")

    # --------------------------------------------------
    # 6. NPC 증거 허용 목록 검증
    # --------------------------------------------------

    for evidence_id in evidence_grants:
        rule = evidence_rules.get(evidence_id)

        if rule is None:
            raise ValueError("존재하지 않는 NPC 증거 허용 ID입니다.")

        if not isinstance(rule, EvidenceRule):
            raise TypeError("NPC 증거 규칙 타입이 올바르지 않습니다.")

        if rule.holder != active_character_id:
            raise ValueError("현재 NPC가 보유하지 않은 증거 ID입니다.")

    # --------------------------------------------------
    # 7. Graph 관계 검색 결과 재검증
    # --------------------------------------------------

    permitted_relations: list[GraphSearchResult] = []
    seen_relations: set[str] = set()

    for result in graph_context.relations:
        if not isinstance(result, GraphSearchResult):
            raise TypeError("Graph 관계 검색 결과 타입이 올바르지 않습니다.")

        if result.edge_id in seen_relations:
            raise ValueError("중복된 Graph 관계 검색 결과입니다.")

        seen_relations.add(result.edge_id)

        edge = trusted_by_id.get(result.edge_id)

        if edge is None:
            raise ValueError("신뢰할 수 없는 Graph 관계 ID입니다.")

        # 원본 관계와 조회 결과 비교
        if (
            result.source_id != edge.source_id
            or result.target_id != edge.target_id
            or result.relation != edge.relation
            or result.truth_status != edge.truth_status
            or result.access_scope != edge.access_scope
            or result.incident_year != edge.incident_year
        ):
            raise ValueError("Graph 관계 원본이 일치하지 않습니다.")

        # 현재 NPC와 연결된 관계인지 확인
        if edge.source_id == active_character_id:
            neighbor_id = edge.target_id

        elif edge.target_id == active_character_id:
            neighbor_id = edge.source_id

        else:
            raise ValueError("현재 NPC와 연결되지 않은 Graph 관계입니다.")

        if result.neighbor_id != neighbor_id:
            raise ValueError("Graph 관계 상대가 일치하지 않습니다.")

        # 현재 NPC에게 승인되지 않은 관계 차단
        if result.edge_id not in relation_grants:
            continue

        # GameState 공개 조건 검증
        if not is_relation_visible(edge, state):
            continue

        # 상대 NPC가 미해금 상태라면 차단
        if (
            neighbor_id in CHARACTER_IDS
            and neighbor_id not in state.unlocked_characters
        ):
            continue

        permitted_relations.append(result)

    # --------------------------------------------------
    # 8. Graph 증거 보유 관계 재검증
    # --------------------------------------------------

    permitted_evidence: list[EvidenceGraphResult] = []
    seen_evidence: set[str] = set()

    for result in graph_context.evidence:
        if not isinstance(result, EvidenceGraphResult):
            raise TypeError("Graph 증거 검색 결과 타입이 올바르지 않습니다.")

        if result.evidence_id in seen_evidence:
            raise ValueError("중복된 Graph 증거 검색 결과입니다.")

        seen_evidence.add(result.evidence_id)

        # 증거 규칙 조회
        # 반드시 for 반복문 내부에서 실행
        rule = evidence_rules.get(result.evidence_id)

        if rule is None:
            raise ValueError("신뢰할 수 없는 Graph 증거 ID입니다.")

        if not isinstance(rule, EvidenceRule):
            raise TypeError("Graph 증거 규칙 타입이 올바르지 않습니다.")

        # 현재 NPC의 증거인지 확인
        if (
            result.holder_id != active_character_id
            or rule.holder != active_character_id
        ):
            raise ValueError("Graph 증거 보유자 정보가 일치하지 않습니다.")

        # 현재 NPC에게 허용되지 않은 증거 차단
        if result.evidence_id not in evidence_grants:
            continue

        # 플레이어의 증거 수집 상태 확인
        evidence_state = state.evidence.get(result.evidence_id)

        if evidence_state is None:
            continue

        if evidence_state.stage not in PolicyEvaluator.VALID_EVIDENCE_STAGES:
            continue

        permitted_evidence.append(result)

    # --------------------------------------------------
    # 9. 최종 허용 ID 구성
    # --------------------------------------------------

    allowed_relation_ids = {result.edge_id for result in permitted_relations}

    allowed_evidence_ids = {result.evidence_id for result in permitted_evidence}

    # --------------------------------------------------
    # 10. RRF 검색 후보 필터링
    # --------------------------------------------------

    filtered_candidates: list[FusedSearchCandidate] = []

    for candidate in candidates:
        if not isinstance(candidate, FusedSearchCandidate):
            raise TypeError("통합 검색 후보 타입이 올바르지 않습니다.")

        if candidate.kind == "chunk":
            # Qdrant 청크는 기존 접근 제어 모듈에서 재검증
            filtered_candidates.append(candidate)

        elif candidate.kind == "relation":
            # Graph 검색 결과에 없는 관계 차단
            if candidate.item_id not in seen_relations:
                raise ValueError("Graph 검색 결과에 없는 관계 후보입니다.")

            if candidate.item_id in allowed_relation_ids:
                filtered_candidates.append(candidate)

        elif candidate.kind == "evidence":
            # Graph 검색 결과에 없는 증거 차단
            if candidate.item_id not in seen_evidence:
                raise ValueError("Graph 검색 결과에 없는 증거 후보입니다.")

            if candidate.item_id in allowed_evidence_ids:
                filtered_candidates.append(candidate)

        else:
            raise ValueError("지원하지 않는 검색 후보 유형입니다.")

    # --------------------------------------------------
    # 11. 최종 Graph 컨텍스트 생성
    # --------------------------------------------------

    filtered_graph = QuestionGraphContext(
        character_id=active_character_id,
        matched_entity_ids=graph_context.matched_entity_ids,
        relations=tuple(permitted_relations),
        evidence=tuple(permitted_evidence),
    )

    return NPCGraphKnowledgeResult(
        candidates=tuple(filtered_candidates),
        graph_context=filtered_graph,
    )
