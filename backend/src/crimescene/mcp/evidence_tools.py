
"""Issue #134 - MCP 증거 검색 결과 접근 제어."""

from collections.abc import Sequence
from typing import TypedDict

from crimescene.api.django_content_client import (
    ContentServiceError,
    DjangoContentClient,
)
from crimescene.retriever.authorized_hybrid_search import AuthorizedRAGChunk
from crimescene.scenario.document_access import (
    can_access_published_e26_document,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState


class EvidenceSearchItem(TypedDict):
    document_id: str
    title: str
    evidence_ids: list[str]
    excerpt: str


class EvidenceSearchPayload(TypedDict):
    items: list[EvidenceSearchItem]






def select_mcp_evidence_results(
    *,
    state: GameState,
    chunks: Sequence[AuthorizedRAGChunk],
    documents: Sequence[PlayerDocument],
    django_client: DjangoContentClient,
    limit: int = 3,
    evaluator: PolicyEvaluator | None = None,
) -> EvidenceSearchPayload:
    """Hybrid RAG와 Django 승인을 통과한 보유 증거만 반환합니다.

    chunks는 반드시 search_authorized_hybrid_context()의
    접근 검증 완료 결과여야 합니다.
    """

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("검색 개수는 정수여야 합니다.")

    if not 1 <= limit <= 5:
        raise ValueError("검색 개수는 1~5개만 허용됩니다.")

    collected = {
        evidence_id
        for evidence_id, evidence in state.evidence.items()
        if evidence.stage in {"found", "resolved"}
    }

    document_map = {document.doc_id: document for document in documents}
    if len(document_map) != len(documents):
        raise ValueError("원본 문서 ID가 중복됐습니다.")

    results: list[EvidenceSearchItem] = []
    seen: set[str] = set()

    for chunk in chunks:
        if chunk.source_type != "player_document":
            continue

        document = document_map.get(chunk.source_id)

        if document is None:
            raise ValueError("신뢰 원본 문서를 찾을 수 없습니다.")

        if document.doc_id in seen:
            continue

        # 게임 내 증거 문서만 허용합니다.
        if (
            document.case_id != state.case_id
            or document.family != "evidence"
            or document.access_scope != "collected_evidence"
        ):
            continue

        # 엔딩 관련 사실과 보호된 콘텐츠는 사용하지 않습니다.
        if document.required_ending is not None:
            continue

        if document.protected_fact_ids:
            continue

        evidence_ids = document.source_evidence_ids

        # Protected evidence must not use the generic return path.
        if "E30" in evidence_ids:
            continue

        if "E26" in evidence_ids and not can_access_published_e26_document(
            state,
            document,
            evaluator,
        ):
            continue

        # 보유 증거에 직접 연결된 문서만 허용합니다.
        if not evidence_ids or not set(evidence_ids).issubset(collected):
            continue

        # 기존 RAG 엔진이 승인한 청크도 원본 본문과 대조합니다.
        if not chunk.content or chunk.content not in document.body:
            raise ValueError("검색 결과가 신뢰 원본 문서와 일치하지 않습니다.")

        approved = True

        for evidence_id in evidence_ids:
            try:
                requirements = django_client.get_evidence_requirements(
                    state.case_id,
                    evidence_id,
                )
            except (ContentServiceError, ValueError):
                # 인증 토큰, 내부 URL, 상세 오류를 노출하지 않습니다.
                raise RuntimeError(
                    "증거 승인 정보를 확인할 수 없습니다."
                ) from None

            if requirements.evidence_id != evidence_id:
                raise PermissionError("증거 승인 응답이 일치하지 않습니다.")

            if not set(requirements.prerequisites).issubset(collected):
                approved = False
                break

        if not approved:
            continue

        seen.add(document.doc_id)

        results.append(
            {
                "document_id": document.doc_id,
                "title": document.title,
                "evidence_ids": list(evidence_ids),
                "excerpt": chunk.content[:400],
            }
        )

        if len(results) >= limit:
            break

    return {"items": results}
