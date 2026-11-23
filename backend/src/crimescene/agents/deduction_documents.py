
"""Issue #132 - Deduction Agent용 증거 문서 접근 제어."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from crimescene.scenario.document_access import (
    select_authorized_player_documents,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState

VALID_STAGES = frozenset({"found", "resolved"})


class DeductionDocument(BaseModel):
    """공개 승인을 받은 문서의 최소 메타데이터."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str
    title: str
    evidence_ids: tuple[str, ...]


def select_visible_deduction_documents(
    *,
    state: GameState,
    documents: Sequence[PlayerDocument],
    evaluator: PolicyEvaluator,
    related_evidence_ids: tuple[str, ...],
    limit: int = 5,
) -> tuple[DeductionDocument, ...]:
    """현재 추리와 관련된 접근 가능 문서만 반환합니다."""

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("PolicyEvaluator가 필요합니다.")

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 20
    ):
        raise ValueError("문서 개수 제한은 1~20이어야 합니다.")

    collected = {
        evidence_id
        for evidence_id, evidence_state in state.evidence.items()
        if evidence_state.stage in VALID_STAGES
    }

    related = set(related_evidence_ids)

    if not related.issubset(collected):
        raise PermissionError("미획득 증거가 포함됐습니다.")

    if not related:
        return ()

    candidates: list[PlayerDocument] = []
    seen_ids: set[str] = set()

    for document in documents:
        if not isinstance(document, PlayerDocument):
            raise TypeError("검증되지 않은 문서 데이터입니다.")

        if document.doc_id in seen_ids:
            raise ValueError("중복된 문서 ID가 존재합니다.")

        seen_ids.add(document.doc_id)

        if document.case_id != state.case_id:
            continue

        # 다른 문서 계열이나 일반 기록은 이번 MVP에서 제외
        if (
            document.family != "evidence"
            or document.access_scope != "collected_evidence"
        ):
            continue

        # 보호 사실이 포함된 문서는 별도 검증 전까지 차단
        if document.protected_fact_ids:
            continue

        linked = set(document.source_evidence_ids)

        # 연결된 모든 증거를 플레이어가 보유해야 합니다.
        if not linked or not linked.issubset(collected):
            continue

        # 현재 추리 대상 증거와 직접 연결되어야 합니다.
        if not linked.intersection(related):
            continue

        candidates.append(document)

    # 기존 문서 공개 정책을 마지막으로 적용합니다.
    authorized = select_authorized_player_documents(
        candidates,
        state,
        evaluator,
    )

    candidate_by_id = {
        document.doc_id: document
        for document in candidates
    }

    results: list[DeductionDocument] = []

    for approved in authorized[:limit]:
        original = candidate_by_id[approved.doc_id]

        results.append(
            DeductionDocument(
                doc_id=approved.doc_id,
                title=approved.title,
                evidence_ids=tuple(
                    sorted(set(original.source_evidence_ids) & related)
                ),
            )
        )

    return tuple(results)
