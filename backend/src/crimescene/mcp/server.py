
"""Issue #134 - 서버 검증 컨텍스트에 바인딩된 MCP Server.

Python 3.13 / MCP Python SDK 2.x
"""

from collections.abc import Mapping, Sequence
from typing import TypedDict

from mcp.server import MCPServer

from crimescene.api.django_content_client import (
    ContentServiceError,
    DjangoContentClient,
)
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.evidence_tools import (
    EvidenceSearchPayload,
    select_mcp_evidence_results,
)
from crimescene.mcp.npc_tools import (
    NPCKnowledgePayload,
    select_mcp_npc_knowledge,
)
from crimescene.retriever.authorized_hybrid_search import (
    search_authorized_hybrid_context,
)
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.game_progress import (
    EXPECTED_EVIDENCE_IDS,
    meets_accusation_requirements,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase


class GameContextPayload(TypedDict):
    phase: str
    current_chapter: str
    unlocked_chapters: list[str]
    unlocked_character_ids: list[str]
    collected_evidence_ids: list[str]
    revision: int


class InvestigationProgressPayload(TypedDict):
    current_chapter: str
    collected_count: int
    total_count: int
    collection_rate: float
    score: int
    total_score: int
    can_accuse: bool

def create_readonly_mcp_server(
    *,
    context: BoundMCPContext,
    evidence_rules: Mapping[str, EvidenceRule],
    npc_cards: Sequence[Mapping[str, object]] = (),
    evaluator: PolicyEvaluator | None = None,
    django_client: DjangoContentClient | None = None,
    rag_resources: NPCRAGResources | None = None,
) -> MCPServer:
    """인증된 플레이어 컨텍스트 전용 MCP Server를 생성합니다."""

    if not isinstance(context, BoundMCPContext):
        raise TypeError("서버 검증 MCP 컨텍스트가 필요합니다.")

    if not isinstance(evidence_rules, Mapping) or not evidence_rules:
        raise ValueError("서버 증거 규칙이 필요합니다.")

    rules: dict[str, EvidenceRule] = {}

    for evidence_id, rule in evidence_rules.items():
        if evidence_id not in EXPECTED_EVIDENCE_IDS:
            raise ValueError("지원하지 않는 증거 ID입니다.")

        if not isinstance(rule, EvidenceRule):
            raise TypeError("증거 규칙 타입이 올바르지 않습니다.")

        rules[evidence_id] = rule.model_copy(deep=True)

    server = MCPServer("CASE-001 Readonly MCP")

    def verified_state_and_progress():
        """MCP Tool 호출마다 최신 상태와 점수 무결성을 검사합니다."""

        state = context.load_verified_state()
        progress = get_collection_progress(state, rules)

        if state.score != progress.score:
            raise ValueError("증거 수집 점수가 일치하지 않습니다.")

        return state, progress

    @server.tool(structured_output=True)
    def get_game_context() -> GameContextPayload:
        """현재 플레이어에게 공개된 게임 진행 정보만 조회합니다."""

        state, _ = verified_state_and_progress()

        return {
            "phase": state.phase.value,
            "current_chapter": state.current_chapter,
            "unlocked_chapters": list(state.unlocked_chapters),
            "unlocked_character_ids": sorted(state.unlocked_characters),
            "collected_evidence_ids": sorted(state.evidence),
            "revision": state.revision,
        }

    @server.tool(structured_output=True)
    def get_investigation_progress() -> InvestigationProgressPayload:
        """현재 증거 수집 및 조사 진행 현황을 조회합니다."""

        state, progress = verified_state_and_progress()

        return {
            "current_chapter": state.current_chapter,
            "collected_count": progress.collected_count,
            "total_count": progress.total_count,
            "collection_rate": round(
                progress.collected_count / progress.total_count * 100,
                2,
            ),
            "score": progress.score,
            "total_score": progress.total,
            "can_accuse": (
                state.phase == GamePhase.INVESTIGATION
                and state.outcome in (None, "ONGOING")
                and state.attempts_left > 0
                and meets_accusation_requirements(state)
            ),
        }

    @server.tool(structured_output=True)
    def get_npc_knowledge() -> NPCKnowledgePayload:
        """현재 선택된 NPC의 승인된 지식만 조회합니다."""

        state, _ = verified_state_and_progress()

        if evaluator is None or django_client is None:
            raise RuntimeError("NPC 지식 조회 서비스가 설정되지 않았습니다.")

        character_id = context.active_character_id

        if character_id is None:
            raise PermissionError("서버에서 검증한 NPC 선택이 필요합니다.")

        if character_id not in state.unlocked_characters:
            raise PermissionError("해금되지 않은 NPC입니다.")

        try:
            approved = django_client.get_approved_npc_cards(
                state.case_id,
                character_id,
            )
        except (ContentServiceError, ValueError):
            raise RuntimeError(
                "NPC 콘텐츠 승인 정보를 확인할 수 없습니다."
            ) from None

        payload = select_mcp_npc_knowledge(
            state=state,
            active_character_id=character_id,
            trusted_cards=npc_cards,
            evaluator=evaluator,
            approved_cards=approved,
        )
        # Django 조회 도중 게임 상태가 변경되었다면 반환을 차단합니다.
        if context.load_verified_state() != state:
            raise RuntimeError("NPC 지식 조회 도중 게임 상태가 변경되었습니다.")

        return payload

    @server.tool(structured_output=True)
    def search_authorized_evidence(
        query: str,
        limit: int = 3,
    ) -> EvidenceSearchPayload:
        """현재 플레이어에게 허용된 보유 증거 문서를 검색합니다."""

        if not isinstance(query, str):
            raise TypeError("검색어는 문자열이어야 합니다.")

        query = query.strip()

        if not 1 <= len(query) <= 200:
            raise ValueError("검색어는 1~200자여야 합니다.")

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 5
        ):
            raise ValueError("검색 개수는 1~5개만 허용됩니다.")

        if rag_resources is None or django_client is None:
            raise RuntimeError("증거 검색 서비스가 설정되지 않았습니다.")

        state, _ = verified_state_and_progress()

        if state.phase != GamePhase.INVESTIGATION:
            raise PermissionError("조사 단계에서만 검색할 수 있습니다.")

        if state.outcome not in (None, "ONGOING"):
            raise PermissionError("종료된 게임에서는 검색할 수 없습니다.")

        chunks = search_authorized_hybrid_context(
            query,
            client=rag_resources.qdrant_client,
            embedder=rag_resources.embedder,
            encoder=rag_resources.encoder,
            trusted_records=rag_resources.trusted_records,
            documents=rag_resources.documents,
            npc_cards=rag_resources.npc_cards,
            state=state,
            evaluator=rag_resources.evaluator,
            active_character_id=None,
            candidate_k=30,
            top_k=20,
        )

        payload = select_mcp_evidence_results(
            state=state,
            chunks=chunks,
            documents=rag_resources.documents,
            django_client=django_client,
            limit=limit,
        )

        # RAG/Django 조회 도중 게임 상태가 변경되었다면
        # 오래된 검색 결과를 반환하지 않습니다.
        latest = context.load_verified_state()

        if latest != state:
            raise RuntimeError("검색 도중 게임 상태가 변경됐습니다.")

        return payload
    return server
