"""CASE-001 권한 검증 기반 Graph RAG 컨텍스트 생성."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    EVIDENCE_IDS,
    is_relation_visible,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"

TRUTH_LABELS = {
    "documented": "자료에 기록됨",
    "witness_statement": "목격자 진술 - 사실 확정 아님",
    "hypothesis": "가설 - 검증되지 않음",
    "uncorroborated_claim": "미확인 주장 - 검증되지 않음",
}


@dataclass(frozen=True, slots=True)
class GraphRagContext:
    """LLM 전달용 Graph RAG 컨텍스트."""

    text: str
    relation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _entity_visible(
    entity_id: str,
    state: GameState,
    allowed_ids: set[str],
) -> bool:
    """GameState 및 서버 승인 목록으로 공개 가능 여부를 판단한다."""

    if entity_id in CHARACTER_IDS:
        return entity_id in state.unlocked_characters

    if entity_id in EVIDENCE_IDS:
        evidence = state.evidence.get(entity_id)

        return (
            evidence is not None
            and evidence.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
        )

    return entity_id in allowed_ids


def _load_labels(
    registry: Sequence[Mapping[str, object]],
    case_id: str,
) -> dict[str, str]:
    """검증된 엔티티 등록 정보에서 표시 이름을 가져온다."""

    labels = {}

    for entity in registry:
        if not isinstance(entity, Mapping):
            raise TypeError("엔티티 등록 정보가 올바르지 않습니다.")

        entity_id = entity.get("entity_id")
        label = entity.get("label")

        if entity.get("case_id") != case_id:
            raise ValueError("엔티티 사건 ID가 일치하지 않습니다.")

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("엔티티 ID가 올바르지 않습니다.")

        if not isinstance(label, str) or not label.strip():
            raise ValueError("엔티티 이름이 올바르지 않습니다.")

        if entity_id in labels:
            raise ValueError("중복 엔티티 ID가 존재합니다.")

        labels[entity_id] = label.strip()

    return labels


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}은 정수여야 합니다.")

    if not 1 <= value <= 100:
        raise ValueError(f"{name}은 1~100 사이여야 합니다.")


def build_graph_rag_context(
    graph: QuestionGraphContext,
    *,
    state: GameState,
    registry: Sequence[Mapping[str, object]],
    trusted_edges: Sequence[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    allowed_entity_ids: Iterable[str] = (),
    allowed_document_ids: Iterable[str] = (),
    max_relations: int = 20,
    max_evidence: int = 10,
) -> GraphRagContext:
    """접근 가능한 그래프 관계를 LLM 참고 문서로 변환한다.

    주의:
        - graph는 검색 후보이며 최종 신뢰 원본이 아니다.
        - trusted_edges는 관리자 비밀 관계를 제외한 검증된 원본이다.
        - 허용 ID 목록은 반드시 서버에서 생성해야 한다.
        - 원문 접근 권한이 없는 문서 ID는 노출하지 않는다.
    """

    if not isinstance(graph, QuestionGraphContext):
        raise TypeError("QuestionGraphContext가 필요합니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if graph.character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    _validate_limit(max_relations, "max_relations")
    _validate_limit(max_evidence, "max_evidence")

    empty = GraphRagContext(
        text="공개 가능한 그래프 근거가 없습니다.",
        relation_ids=(),
        evidence_ids=(),
    )

    # 잠긴 NPC의 정보는 텍스트 생성 전에 차단
    if graph.character_id not in state.unlocked_characters:
        return empty

    if isinstance(allowed_entity_ids, (str, bytes)):
        raise TypeError("허용 엔티티 목록 형식이 올바르지 않습니다.")

    if isinstance(allowed_document_ids, (str, bytes)):
        raise TypeError("허용 문서 목록 형식이 올바르지 않습니다.")

    allowed_entities = set(allowed_entity_ids)
    allowed_documents = set(allowed_document_ids)

    if any(not isinstance(item, str) for item in allowed_entities):
        raise TypeError("허용 엔티티 ID 형식이 올바르지 않습니다.")

    if any(not isinstance(item, str) for item in allowed_documents):
        raise TypeError("허용 문서 ID 형식이 올바르지 않습니다.")

    labels = _load_labels(registry, state.case_id)

    # Neo4j 조회 결과와 대조할 신뢰 원본
    trusted_by_id = {}

    for edge in trusted_edges:
        if not isinstance(edge, RelationshipSourceEdge):
            raise TypeError("검증되지 않은 관계 데이터입니다.")

        if edge.case_id != state.case_id:
            raise ValueError("관계 사건 ID가 일치하지 않습니다.")

        if edge.edge_id in trusted_by_id:
            raise ValueError("중복 관계 ID가 존재합니다.")

        trusted_by_id[edge.edge_id] = edge

    lines = [
        "[GRAPH_RAG_CONTEXT]",
        "아래 내용은 현재 게임 상태에서 허용된 참고 데이터입니다.",
        "진술·가설·미확인 주장을 확정된 사실처럼 답변하지 마세요.",
        "근거에 없는 사실을 새로 만들어내지 마세요.",
    ]

    relation_ids = []
    evidence_ids = []
    seen_relations = set()
    seen_evidence = set()

    # 1. 인물·장소·사건 관계
    for result in graph.relations:
        edge = trusted_by_id.get(result.edge_id)

        if edge is None:
            raise ValueError("신뢰할 수 없는 관계 ID가 검색됐습니다.")

        # 검색 결과가 원본 관계의 내용을 바꾸지 못하도록 검증
        if (
            result.source_id != edge.source_id
            or result.target_id != edge.target_id
            or result.relation != edge.relation
            or result.truth_status != edge.truth_status
            or result.access_scope != edge.access_scope
            or result.incident_year != edge.incident_year
        ):
            raise ValueError("원본과 관계 검색 결과가 일치하지 않습니다.")

        actor_id = graph.character_id

        if actor_id == edge.source_id:
            neighbor_id = edge.target_id
        elif actor_id == edge.target_id:
            neighbor_id = edge.source_id
        else:
            raise ValueError("대화 NPC와 연결되지 않은 관계입니다.")

        if result.neighbor_id != neighbor_id:
            raise ValueError("관계 상대 엔티티가 일치하지 않습니다.")

        # 기존 GameState 관계 접근 정책 재검증
        if not is_relation_visible(edge, state):
            continue

        # 양쪽 엔티티 모두 공개 가능한 경우만 포함
        if not all(
            _entity_visible(entity_id, state, allowed_entities)
            for entity_id in (edge.source_id, edge.target_id)
        ):
            continue

        if edge.edge_id in seen_relations:
            continue

        seen_relations.add(edge.edge_id)

        source_name = labels.get(edge.source_id, edge.source_id)
        target_name = labels.get(edge.target_id, edge.target_id)

        truth_label = TRUTH_LABELS[edge.truth_status]

        # 원문 문서 ID는 서버가 허용한 경우에만 포함
        visible_documents = tuple(
            dict.fromkeys(
                doc_id for doc_id in edge.source_doc_ids if doc_id in allowed_documents
            )
        )

        lines.append(f"- 관계 {edge.edge_id}: {source_name} → {target_name}")
        lines.append(f"  관계 유형: {edge.relation}")
        lines.append(f"  사건 연도: {edge.incident_year}")
        lines.append(f"  근거 성격: {truth_label}")

        if visible_documents:
            lines.append("  열람 허용 원문 ID: " + ", ".join(visible_documents))

        relation_ids.append(edge.edge_id)

        if len(relation_ids) >= max_relations:
            break

    # 2. 증거 보유 관계
    for item in graph.evidence:
        evidence_id = item.evidence_id

        rule = evidence_rules.get(evidence_id)

        if rule is None or not isinstance(rule, EvidenceRule):
            raise ValueError("검증되지 않은 증거 규칙입니다.")

        if item.holder_id != graph.character_id or rule.holder != graph.character_id:
            raise ValueError("증거 보유자 정보가 일치하지 않습니다.")

        if not _entity_visible(evidence_id, state, allowed_entities):
            continue

        if evidence_id in seen_evidence:
            continue

        seen_evidence.add(evidence_id)

        lines.append(f"- 수집 증거 {evidence_id}: {rule.name}")
        lines.append(f"  보유자: {labels.get(item.holder_id, item.holder_id)}")
        lines.append("  상태: 플레이어가 수집한 증거")

        evidence_ids.append(evidence_id)

        if len(evidence_ids) >= max_evidence:
            break

    if not relation_ids and not evidence_ids:
        return empty

    lines.append("[/GRAPH_RAG_CONTEXT]")

    return GraphRagContext(
        text="\n".join(lines),
        relation_ids=tuple(relation_ids),
        evidence_ids=tuple(evidence_ids),
    )
