
"""Issue #132 - Deduction Agent용 공개 관계 필터."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from crimescene.retriever.graph_search import is_relation_visible
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge


class DeductionRelation(BaseModel):
    """플레이어에게 공개 가능한 관계 정보만 보존합니다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str
    source_id: str
    target_id: str
    relation: str
    truth_status: str
    evidence_ids: tuple[str, ...]


def select_visible_deduction_relations(
    *,
    state: GameState,
    trusted_edges: Sequence[RelationshipSourceEdge],
    related_evidence_ids: tuple[str, ...],
    limit: int = 5,
) -> tuple[DeductionRelation, ...]:
    """보유 증거와 연결된 공개 관계만 선택합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("관계 개수 제한은 1~20이어야 합니다.")

    related = set(related_evidence_ids)

    if not related.issubset(set(state.evidence)):
        raise PermissionError("미획득 증거가 포함됐습니다.")

    # 해금된 NPC, 공개 피해자, 이번 추론에 사용한 증거만 허용
    visible_entities = set(state.unlocked_characters) | {"V01"} | related

    results: list[DeductionRelation] = []

    for edge in trusted_edges:
        if not isinstance(edge, RelationshipSourceEdge):
            raise TypeError("검증되지 않은 관계 데이터입니다.")

        if edge.case_id != state.case_id:
            continue

        # 엔딩 전용 관계는 추론 단계에서 공개하지 않습니다.
        if edge.access_scope == "ending_only":
            continue

        if not {edge.source_id, edge.target_id}.issubset(visible_entities):
            continue

        # 기존 GameState 기반 공개 정책 재사용
        if not is_relation_visible(edge, state):
            continue

        # 추론 대상 증거와 실제 연결된 관계만 반환
        anchors = (
            set(edge.required_evidence)
            | {edge.source_id, edge.target_id}
        ) & related

        if not anchors:
            continue

        results.append(
            DeductionRelation(
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation=edge.relation,
                truth_status=edge.truth_status,
                evidence_ids=tuple(sorted(anchors)),
            )
        )

        if len(results) >= limit:
            break

    return tuple(results)
