
"""Issue #134 - MCP 증거 검색 접근 제어 테스트."""

from types import SimpleNamespace

import pytest
from mcp import Client

from crimescene.api.django_content_client import (
    ContentServiceError,
    EvidenceRequirements,
)
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.evidence_tools import select_mcp_evidence_results
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.retriever.authorized_hybrid_search import AuthorizedRAGChunk
from crimescene.scenario.game_progress import (
    create_initial_state,
    transition_phase,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)


class FakeDjango:
    def __init__(self, *, prerequisites=(), fail=False):
        self.prerequisites = list(prerequisites)
        self.fail = fail

    def get_evidence_requirements(self, case_id, evidence_id):
        if self.fail:
            raise ContentServiceError("Service unavailable")

        return EvidenceRequirements(
            evidence_id=evidence_id,
            prerequisites=self.prerequisites,
            player_unlock_verification_required=True,
        )


def make_state(*, collected=("E01",)):
    state = transition_phase(
        create_initial_state("mcp-evidence-test"),
        GamePhase.INVESTIGATION,
    )
    state.evidence = {
        evidence_id: EvidenceState(stage="found")
        for evidence_id in collected
    }
    return state


def make_document(*, protected=False, evidence_ids=None):
    return PlayerDocument(
        doc_id="DOC-001",
        case_id="CASE-001",
        title="확보된 증거 기록",
        body="현재 게임에서 플레이어에게 공개 가능한 증거 내용",
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=evidence_ids or ["E01"],
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=["E01"],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=["SECRET"] if protected else [],
        incident_year=None,
        incident_years=[],
        source_refs=[],
        record_id="RECORD-001",
        point_id="POINT-001",
        policy_id="POL-001",
        state_version="1",
        content_version="1",
        build_id="test",
        content_hash="test-hash",
        search_text="공개 가능한 증거 내용",
    )


def make_chunk():
    return AuthorizedRAGChunk(
        source_id="DOC-001",
        source_type="player_document",
        content="공개 가능한 증거 내용",
    )


def search(*, state=None, document=None, django=None):
    return select_mcp_evidence_results(
        state=state or make_state(),
        chunks=[make_chunk()],
        documents=[document or make_document()],
        django_client=django or FakeDjango(),
    )


def test_authorized_collected_evidence_returned():
    result = search()

    assert len(result["items"]) == 1
    assert result["items"][0]["document_id"] == "DOC-001"
    assert result["items"][0]["evidence_ids"] == ["E01"]


def test_uncollected_evidence_blocked():
    state = make_state(collected=())

    result = search(state=state)

    assert result["items"] == []


def test_protected_document_blocked():
    result = search(document=make_document(protected=True))

    assert result["items"] == []


def test_document_with_uncollected_dependency_blocked():
    document = make_document(evidence_ids=["E01", "E02"])

    result = search(document=document)

    assert result["items"] == []


def test_django_prerequisite_not_met():
    result = search(django=FakeDjango(prerequisites=("E02",)))

    assert result["items"] == []


def test_django_failure_closed():
    with pytest.raises(RuntimeError, match="승인 정보"):
        search(django=FakeDjango(fail=True))


def test_untrusted_content_rejected():
    chunk = AuthorizedRAGChunk(
        source_id="DOC-001",
        source_type="player_document",
        content="서버 원본에 없는 조작된 내용",
    )

    with pytest.raises(ValueError, match="원본"):
        select_mcp_evidence_results(
            state=make_state(),
            chunks=[chunk],
            documents=[make_document()],
            django_client=FakeDjango(),
        )


def test_limit_validation():
    with pytest.raises(ValueError, match="1~5"):
        select_mcp_evidence_results(
            state=make_state(),
            chunks=[make_chunk()],
            documents=[make_document()],
            django_client=FakeDjango(),
            limit=10,
        )

@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_protocol_server(monkeypatch, state, *, django=None):
    # 기존 증거 진행 상태와 점수를 일치시킵니다.
    state.score = 2 if "E01" in state.evidence else 0

    context = BoundMCPContext.from_owned_game_state(
        state=state,
        load_state=lambda _: state,
    )

    resources = SimpleNamespace(
        qdrant_client=None,
        embedder=None,
        encoder=None,
        trusted_records=(),
        documents=(make_document(),),
        npc_cards=(),
        evaluator=PolicyEvaluator({}),
    )

    # 검색 결과는 Mock하지만 이후 MCP 접근 검증은 실제 실행합니다.
    monkeypatch.setattr(
        "crimescene.mcp.server.search_authorized_hybrid_context",
        lambda query, **kwargs: [make_chunk()],
    )

    server = create_readonly_mcp_server(
        context=context,
        evidence_rules={
            "E01": EvidenceRule(
                name="첫 번째 증거",
                score=2,
                holder="C01",
                prerequisites=[],
                presentation=[],
                q=[],
            )
        },
        rag_resources=resources,
        django_client=django if django is not None else FakeDjango(),
    )

    return server

@pytest.mark.anyio
async def test_evidence_search_success_via_mcp(monkeypatch):
    state = make_state()
    server = make_protocol_server(monkeypatch, state)
    before = state.model_dump(mode="json")

    async with Client(server) as client:
        result = await client.call_tool(
            "search_authorized_evidence",
            {"query": "증거 기록", "limit": 3},
        )

    assert not result.is_error
    assert result.structured_content is not None

    data = result.structured_content
    assert len(data["items"]) == 1
    assert data["items"][0]["document_id"] == "DOC-001"
    assert data["items"][0]["evidence_ids"] == ["E01"]

    # 반환 데이터에 세션이나 인증 정보를 포함하지 않습니다.
    assert state.session_id not in str(data)
    assert "session_id" not in data

    # 읽기 전용 실행 검증
    assert state.model_dump(mode="json") == before


@pytest.mark.anyio
async def test_uncollected_evidence_blocked_via_mcp(monkeypatch):
    state = make_state(collected=())
    server = make_protocol_server(monkeypatch, state)

    async with Client(server) as client:
        result = await client.call_tool(
            "search_authorized_evidence",
            {"query": "비공개 증거"},
        )

    assert not result.is_error
    assert result.structured_content == {"items": []}


@pytest.mark.anyio
async def test_django_failure_blocks_evidence_mcp(monkeypatch):
    state = make_state()
    server = make_protocol_server(
        monkeypatch,
        state,
        django=FakeDjango(fail=True),
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "search_authorized_evidence",
            {"query": "증거 기록"},
        )

    assert result.is_error
    assert result.structured_content is None

    # Django 내부 오류 메시지를 그대로 공개하지 않습니다.
    assert "Service unavailable" not in str(result.content)


@pytest.mark.anyio
async def test_evidence_search_rejects_state_change(monkeypatch):
    state = make_state()
    server = make_protocol_server(monkeypatch, state)

    def changing_search(query, **kwargs):
        # 검색 중 다른 요청이 게임 상태를 변경한 상황
        state.revision += 1
        return [make_chunk()]

    monkeypatch.setattr(
        "crimescene.mcp.server.search_authorized_hybrid_context",
        changing_search,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "search_authorized_evidence",
            {"query": "증거 기록"},
        )

    assert result.is_error
    assert result.structured_content is None