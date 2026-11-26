"""Issue #62 - 게임 시작, 저장, 이어하기 및 NPC 선택 API."""

import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from crimescene.api.e30_consent_service import (
    E30ConsentRequest,
    e30_consent_available,
    grant_e30_player_consent,
)

from crimescene.api.ending_image_service import (
    IMAGE_HEADERS,
    EndingImagesResponse,
    build_ending_images_response,
    resolve_ending_image,
)
from mcp.server import MCPServer
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from pydantic import BaseModel, ConfigDict, Field, field_validator

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentType,
)
from crimescene.agents.npc_agent import (
    NPCAgent,
    NPCAgentResult,
    NPCDisplayError,
    NPCEvidenceReactionError,
)
from crimescene.agents.orchestrator import (
    AgentExecutionTimeout,
    AgentOrchestrator,
)
from crimescene.agents.registry import AgentRegistry
from crimescene.api.agent_http import create_agent_router
from crimescene.api.django_content_client import (
    ContentServiceError,
    ContentServiceNotFoundError,
    DjangoContentClient,
)
from crimescene.api.story_event_progress import (
    stage_story_events,
)
from crimescene.chat.llm_client import LLMProviderError
from crimescene.chat.npc_history_display import render_stored_npc_message
from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.mcp.context import BoundMCPContext
from crimescene.mcp.server import create_readonly_mcp_server
from crimescene.retriever.graph_search import (
    is_relation_visible,
    search_character_relations,
)
from crimescene.scenario.accusation import AccusationStatus, can_accuse
from crimescene.scenario.accusation_service import (
    submit_accusation_request_atomic,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.chapter_progress import (
    ChapterUnlockRule,
    advance_chapter_atomic,
    can_revisit_investigation_chapter,
    next_chapter_choices,
)
from crimescene.scenario.document_access import select_authorized_player_documents
from crimescene.scenario.e26_section_policy import (
    can_access_e26_section_for_state,
)
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.evidence_service import collect_evidence_atomic
from crimescene.scenario.game_progress import (
    EXPECTED_EVIDENCE_IDS,
    create_initial_state,
    meets_accusation_requirements,
    transition_phase,
)
from crimescene.scenario.loaders.unlock_graph_loader import Case001UnlockRules
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository
from crimescene.trigger.npc_trigger import NPCTriggerRule

# ============================================================
# Constants
# ============================================================

COOKIE_NAME = "case001_owner"

TOTAL_SCORE = 21

COOKIE_MAX_AGE = 60 * 60 * 24 * 7

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 플레이어가 API로 입력하는 NPC 질문의 최대 길이
MAX_PLAYER_QUESTION_LENGTH = 200
# ============================================================
# Response Schemas
# ============================================================


class CollectionResponse(BaseModel):
    """증거 수집 진행 상태."""

    score: int
    total: int


class GameResponse(BaseModel):
    """React 프론트엔드에 반환할 게임 상태."""

    sessionId: str
    phase: GamePhase

    currentChapter: str
    unlockedChapters: list[str]

    activeCharacterId: str
    unlockedCharacters: list[str]

    collection: CollectionResponse
    canAccuse: bool

    attemptsLeft: int
    outcome: str | None

    revision: int
    events: list[dict[str, str]]
    e30ConsentAvailable: bool = False
    e30ConsentGranted: bool = False


class ContentChapterResponse(BaseModel):
    """플레이어에게 공개할 챕터 기본 정보."""

    code: str
    order: int
    title: str


class GameContentOverviewResponse(BaseModel):
    """게임 세션에 연결된 공개 사건 정보."""

    caseId: str
    title: str
    chapters: list[ContentChapterResponse]


class GameSceneResponse(BaseModel):
    """플레이어에게 공개하는 스토리 장면."""

    sceneId: str
    chapter: str
    title: str
    sceneText: str


class ChapterAdvanceRequest(BaseModel):
    """챕터 전환 요청 계약."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expectedRevision: int = Field(ge=0)
    targetChapter: ChapterCode | None = None


class ChatRequest(BaseModel):
    """플레이어의 NPC 대화 요청."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        max_length=MAX_PLAYER_QUESTION_LENGTH,
    )

    presentedEvidenceId: str | None = Field(
        default=None,
        pattern=r"^E(?:0[1-9]|[12][0-9]|30)$",
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        question = value.strip()

        if not question:
            raise ValueError("질문이 비어 있습니다.")

        return question


class ChatResponse(BaseModel):
    """검증된 NPC 응답과 최신 게임 상태."""

    characterId: str
    display_text: str
    game: GameResponse


class ChatMessageResponse(BaseModel):
    userMessage: str
    displayText: str


class ChatHistoryResponse(BaseModel):
    sessionId: str
    characterId: str
    messages: list[ChatMessageResponse]


# ============================================================
# FastAPI Application Factory
# ============================================================


class EvidenceCollectResponse(BaseModel):
    """획득 결과와 서버가 갱신한 게임 상태."""

    evidenceId: str
    created: bool
    collectedCount: int
    totalCount: int
    newlyUnlockedCharacters: list[str]
    game: GameResponse


class EvidenceItemResponse(BaseModel):
    evidenceId: str
    name: str
    score: int
    stage: str


class EvidenceListResponse(BaseModel):
    items: list[EvidenceItemResponse]
    collectedCount: int
    totalCount: int


class EvidenceAvailableItemResponse(BaseModel):
    evidenceId: str
    name: str
    score: int


class EvidenceAvailableResponse(BaseModel):
    items: list[EvidenceAvailableItemResponse]


class EvidenceDocumentResponse(BaseModel):
    id: str
    label: str
    title: str
    body: str


class EvidenceDetailResponse(BaseModel):
    id: str
    title: str
    body: str | None
    holderId: str
    acquiredBy: str | None
    confirmedRelations: list[dict[str, str]]
    documents: list[EvidenceDocumentResponse] = Field(default_factory=list)


class ProgressResponse(BaseModel):
    collection: CollectionResponse
    collectedCount: int
    totalCount: int
    collectionRate: float
    canAccuse: bool
    attemptsLeft: int


class RelationshipNodeResponse(BaseModel):
    id: str
    label: str


class RelationshipEdgeResponse(BaseModel):
    id: str
    sourceId: str
    targetId: str
    relation: str


class RelationshipResponse(BaseModel):
    nodes: list[RelationshipNodeResponse]
    edges: list[RelationshipEdgeResponse]


class AccusationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suspectId: str = Field(pattern=r"^C(?:0[1-9]|10)$")
    expectedRevision: int = Field(ge=0)


class AccusationResponse(BaseModel):
    result: AccusationStatus
    attemptsLeft: int
    game: GameResponse


class EndingTruthResponse(BaseModel):
    perpetratorId: str
    motive: str
    causeOfDeath: str
    crimeMethod: str


class EndingResponse(BaseModel):
    outcome: str
    title: str
    message: str
    deepEligible: bool
    truth: EndingTruthResponse | None
    game: GameResponse


def create_app(
    repository: SQLiteCase001Repository,
    *,
    session_secret: str,
    secure_cookie: bool = False,
    dialogue_resources: NPCRAGResources | None = None,
    dialogue_policies: Mapping[str, AccessPolicy] | None = None,
    dialogue_triggers: tuple[NPCTriggerRule, ...] = (),
    dialogue_flag_config: Case001UnlockRules | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """서버 관리 게임 상태와 FastAPI를 연결합니다."""

    # --------------------------------------------------------
    # 1. 초기 설정 검증
    # --------------------------------------------------------

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("SQLiteCase001Repository가 필요합니다.")

    if not isinstance(session_secret, str):
        raise TypeError("세션 비밀키는 문자열이어야 합니다.")

    if len(session_secret.encode("utf-8")) < 32:
        raise ValueError("세션 비밀키는 최소 32바이트여야 합니다.")

    if not isinstance(secure_cookie, bool):
        raise TypeError("secure_cookie는 bool이어야 합니다.")

    app = FastAPI(
        title="CASE-001 Game API",
        description="마지막 기록: 사라진 공동체",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --------------------------------------------------------
    # 2. CORS 설정
    # --------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # --------------------------------------------------------
    # 3. 서비스 및 저장소
    # --------------------------------------------------------

    secret = session_secret.encode("utf-8")

    # --------------------------------------------------------
    # 4. 세션 소유권 검증
    # --------------------------------------------------------

    def owner_token(session_id: str) -> str:
        """세션별 HMAC 소유권 토큰을 생성합니다."""

        return hmac.new(
            secret,
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def require_owner(
        session_id: str,
        cookie: str | None,
    ) -> None:
        """세션 소유권이 없는 요청을 차단합니다."""

        if not isinstance(session_id, str):
            raise HTTPException(
                status_code=404,
                detail="게임을 찾을 수 없습니다.",
            )

        if not 1 <= len(session_id) <= 128:
            raise HTTPException(
                status_code=404,
                detail="게임을 찾을 수 없습니다.",
            )

        expected = owner_token(session_id)

        if not hmac.compare_digest(
            cookie or "",
            expected,
        ):
            raise HTTPException(
                status_code=404,
                detail="게임을 찾을 수 없습니다.",
            )

    # --------------------------------------------------------
    # 5. 서버 게임 상태 조회
    # --------------------------------------------------------

    def load_owned_state(
        session_id: str,
        cookie: str | None,
    ) -> GameState:
        """소유권 검증 후 SQLite에서 최신 상태를 조회합니다."""

        require_owner(
            session_id,
            cookie,
        )

        try:
            state = repository.load_state(
                session_id,
            )

        except ValueError:
            raise HTTPException(
                status_code=404,
                detail="게임을 찾을 수 없습니다.",
            ) from None

        runtime_version = getattr(
            app.state,
            "content_version",
            "case001_v7_1",
        )

        if state.content_version != runtime_version:
            raise HTTPException(
                status_code=409,
                detail="Game content version mismatch",
            )

        return state

    def load_owned_request(
        session_id: str,
        request: Request,
        legacy_cookie: str | None,
    ) -> GameState:
        """게임별 쿠키를 우선 사용하고 기존 쿠키와도 호환합니다."""

        scoped_cookie = request.cookies.get(f"{COOKIE_NAME}_{session_id}")

        return load_owned_state(
            session_id,
            scoped_cookie or legacy_cookie,
        )

    def create_owner_scoped_mcp_server(
        session_id: str,
        request: Request,
        legacy_cookie: str | None = None,
    ) -> MCPServer:
        """FastAPI 인증을 통과한 세션 전용 MCP Server를 생성합니다."""

        if request.app is not app:
            raise HTTPException(
                status_code=403,
                detail="허용되지 않은 애플리케이션 요청입니다.",
            )

        # 1. 반드시 기존 HMAC 쿠키 인증을 먼저 수행합니다.
        state = load_owned_request(
            session_id,
            request,
            legacy_cookie,
        )

        # 2. 현재 NPC 선택과 게임 revision을 검증합니다.
        selection = repository.load_selection(state.session_id)

        if (
            selection is None
            or selection[1] != state.revision
            or selection[0] not in state.unlocked_characters
        ):
            raise HTTPException(
                status_code=409,
                detail="NPC 선택 상태가 일치하지 않습니다.",
            )

        # 3. 서버에서 로딩한 리소스만 사용합니다.
        resources = getattr(
            app.state,
            "dialogue_resources",
            dialogue_resources,
        )
        django_client = getattr(
            app.state,
            "django_content_client",
            None,
        )

        if not isinstance(resources, NPCRAGResources):
            raise HTTPException(
                status_code=503,
                detail="RAG 서비스가 준비되지 않았습니다.",
            )

        if not resources.evidence_rules:
            raise HTTPException(
                status_code=503,
                detail="증거 규칙이 준비되지 않았습니다.",
            )

        if not isinstance(django_client, DjangoContentClient):
            raise HTTPException(
                status_code=503,
                detail="콘텐츠 승인 서비스를 사용할 수 없습니다.",
            )

        # 4. 인증 완료 후 서버 관리 컨텍스트를 생성합니다.
        context = BoundMCPContext.from_owned_game_state(
            state=state,
            load_state=repository.load_state,
            active_character_id=selection[0],
        )

        # 5. 사용자 세션마다 독립된 MCP Server를 생성합니다.
        return create_readonly_mcp_server(
            context=context,
            evidence_rules=resources.evidence_rules,
            npc_cards=resources.npc_cards,
            evaluator=resources.evaluator,
            django_client=django_client,
            rag_resources=resources,
        )

    # 외부 HTTP 경로를 등록하지 않고 앱 내부에서만 사용합니다.
    app.state.create_owner_scoped_mcp_server = (
        create_owner_scoped_mcp_server
    )

    # --------------------------------------------------------
    # 6. 공통 게임 응답 생성
    # --------------------------------------------------------
    def stage_game_story_events(
        state: GameState,
    ) -> GameState:
        """서버에서 승인한 이벤트만 저장 예정 상태에 추가합니다."""

        bindings = getattr(
            app.state,
            "story_event_bindings",
            None,
        )

        conditions = getattr(
            app.state,
            "story_event_conditions",
            None,
        )

        # 기능이 비활성화된 경우 기존 상태를 유지합니다.
        if bindings is None and conditions is None:
            return state

        if (
            not isinstance(bindings, Mapping)
            or not isinstance(conditions, Mapping)
        ):
            raise ContentServiceError(
                "Story Event configuration unavailable"
            )

        def fetch_approved(event_key: str):
            client = getattr(
                app.state,
                "django_content_client",
                None,
            )

            if not isinstance(client, DjangoContentClient):
                raise ContentServiceError(
                    "Story Event content service unavailable"
                )

            return client.get_approved_story_event(
                state.case_id,
                event_key,
            )

        try:
            return stage_story_events(
                state,
                bindings=bindings,
                conditions=conditions,
                fetch_approved_event=fetch_approved,
            )

        except (ValueError, TypeError):
            raise ContentServiceError(
                "Invalid Story Event configuration"
            ) from None

    def game_response(
        state: GameState,
        *,
        events: list[dict[str, str]] | None = None,
    ) -> GameResponse:
        """서버 상태를 프론트엔드 응답 형식으로 변환합니다."""

        selection = repository.load_selection(
            state.session_id,
        )

        if selection is None:
            raise HTTPException(
                status_code=409,
                detail="NPC 선택 정보가 없습니다.",
            )

        active_npc, selection_revision = selection

        if selection_revision != state.revision:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 일치하지 않습니다.",
            )

        if active_npc not in state.unlocked_characters:
            raise HTTPException(
                status_code=409,
                detail="현재 NPC 선택 상태가 올바르지 않습니다.",
            )

        # 실제 지목 판정은 #29 엔진에서 수행합니다.
        # 여기서는 화면 표시용 최소 진입 조건만 계산합니다.
        accusation_allowed = (
            state.phase
            in (
                GamePhase.INVESTIGATION,
                GamePhase.ACCUSATION,
            )
            and state.outcome in (None, "ONGOING")
            and state.attempts_left > 0
            and meets_accusation_requirements(state)
        )

        resources = getattr(
            app.state,
            "dialogue_resources",
            dialogue_resources,
        )

        rules = getattr(resources, "evidence_rules", None)
        total_score = TOTAL_SCORE

        if rules and not set(rules).issubset(EXPECTED_EVIDENCE_IDS):
            try:
                accusation_allowed = can_accuse(state, rules)
                progress = get_collection_progress(state, rules)
                total_score = progress.total
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=409,
                    detail="Invalid game progress data",
                ) from None

        return GameResponse(
            sessionId=state.session_id,
            phase=state.phase,
            activeCharacterId=active_npc,
            unlockedCharacters=list(state.unlocked_characters),
            collection=CollectionResponse(
                score=state.score,
                total=total_score,
            ),
            canAccuse=accusation_allowed,
            attemptsLeft=state.attempts_left,
            outcome=state.outcome,
            revision=state.revision,
            events=events if events is not None else [],
            currentChapter=state.current_chapter,
            unlockedChapters=list(state.unlocked_chapters),
            e30ConsentAvailable=e30_consent_available(
                state,
                getattr(app.state, "e30_approval_check", None),
            ),
            e30ConsentGranted=state.e30_player_consent,
        )

    # ========================================================
    # API 1. 새 게임 생성
    # ========================================================

    @app.post(
        "/api/games",
        response_model=GameResponse,
        status_code=201,
    )
    async def create_game(
        request: Request,
        response: Response,
    ) -> GameResponse:
        """새 게임 세션과 초기 GameState를 생성합니다."""

        # 클라이언트가 점수·증거·권한을 지정하지 못하도록 차단합니다.
        if await request.body():
            raise HTTPException(
                status_code=422,
                detail=("새 게임 생성에는 요청 본문이 필요하지 않습니다."),
            )

        # 충돌 가능성이 매우 낮은 서버 생성 세션 ID
        session_id = secrets.token_urlsafe(32)

        state = create_initial_state(
            session_id,
            content_version=getattr(
                app.state,
                "content_version",
                "case001_v7_1",
            ),
        )

        # 최초 NPC는 C01입니다.
        repository.save_selection(
            state.session_id,
            "C01",
            state.revision,
        )

        # 게임 상태를 SQLite에 영구 저장합니다.
        repository.register_state(
            state,
        )

        # 클라이언트 JavaScript에서 읽을 수 없는 쿠키
        response.set_cookie(
            key=COOKIE_NAME,
            value=owner_token(session_id),
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
            path="/api/games",
        )

        # 게임별 소유권을 보존합니다. 기존 쿠키는 이전 클라이언트 호환용입니다.
        response.set_cookie(
            key=f"{COOKIE_NAME}_{session_id}",
            value=owner_token(session_id),
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
            path=f"/api/games/{session_id}",
        )

        return game_response(state)

    # ========================================================
    # API 2. 게임 상태 조회 / 이어하기
    # ========================================================

    @app.get(
        "/api/games/{session_id}",
        response_model=GameResponse,
    )
    def get_game(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameResponse:
        """기존 게임의 저장된 진행 상태를 불러옵니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        return game_response(state)

    # ========================================================
    # API: 챕터 전환
    # ========================================================

    @app.post(
        "/api/games/{session_id}/chapter/advance",
        response_model=GameResponse,
    )
    def advance_game_chapter(
        session_id: str,
        payload: ChapterAdvanceRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameResponse:
        """서버 해금 규칙에 따라 다음 챕터로 진행합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if (
            state.content_version == "case001_v7_1"
            and payload.targetChapter is not None
        ):
            raise HTTPException(
                status_code=422,
                detail="Legacy chapter does not accept targetChapter",
            )

        if state.revision != payload.expectedRevision:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            )

        if (
            state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise HTTPException(
                status_code=409,
                detail="챕터를 진행할 수 없는 상태입니다.",
            )

        choices = next_chapter_choices(state)

        if not choices:
            raise HTTPException(
                status_code=409,
                detail="No next chapter available",
            )

        if payload.targetChapter is None:
            if len(choices) != 1:
                raise HTTPException(
                    status_code=422,
                    detail="Select targetChapter",
                )

            next_chapter = choices[0]

        else:
            next_chapter = payload.targetChapter

            if (
                next_chapter not in choices
                and not can_revisit_investigation_chapter(
                    state, next_chapter
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Chapter transition not allowed",
                )

        rules = getattr(
            request.app.state,
            "chapter_unlock_rules",
            None,
        )

        if not isinstance(rules, Mapping):
            raise HTTPException(
                status_code=503,
                detail="챕터 진행 규칙을 사용할 수 없습니다.",
            )

        rule = rules.get(next_chapter)

        if (
            not isinstance(rule, ChapterUnlockRule)
            or rule.target_chapter != next_chapter
        ):
            raise HTTPException(
                status_code=503,
                detail="챕터 진행 규칙을 사용할 수 없습니다.",
            )

        try:
            updated = advance_chapter_atomic(
                repository,
                session_id,
                rule=rule,
                expected_revision=payload.expectedRevision,
                stage_events=stage_game_story_events,
            )

        except ContentServiceError:
            raise HTTPException(
                status_code=503,
                detail="스토리 이벤트 승인 정보를 확인할 수 없습니다.",
            ) from None

        except PermissionError:
            raise HTTPException(
                status_code=409,
                detail="챕터 진행 조건이 충족되지 않았습니다.",
            ) from None

        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            ) from None

        return game_response(
            updated,
            events=[
                {
                    "type": "CHAPTER_CHANGED",
                    "chapter": updated.current_chapter,
                },
                {
                    "type": "GAME_PROGRESS_UPDATED",
                },
            ],
        )

    # ========================================================
    # API: 게시된 사건·챕터 개요 조회 (Django 콘텐츠 연동)
    # ========================================================

    @app.get(
        "/api/games/{session_id}/content/overview",
        response_model=GameContentOverviewResponse,
    )
    def get_game_content_overview(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameContentOverviewResponse:
        """소유자가 접근 가능한 게시 사건의 개요만 반환합니다."""

        # 클라이언트의 case_id를 신뢰하지 않고, 서버의 게임 상태를 조회합니다.
        state = load_owned_request(session_id, request, case001_owner)

        client = getattr(request.app.state, "django_content_client", None)
        if not isinstance(client, DjangoContentClient):
            raise HTTPException(
                status_code=503,
                detail="콘텐츠 서비스를 사용할 수 없습니다.",
            )

        try:
            overview = client.get_case_overview(state.case_id)
        except (ContentServiceError, ValueError):
            # 내부 서비스 URL, 인증 토큰, 상세 오류를 외부에 노출하지 않습니다.
            raise HTTPException(
                status_code=503,
                detail="콘텐츠 조회에 실패했습니다.",
            ) from None

        if (
            overview.case.case_id != state.case_id
            or overview.case.status != "PUBLISHED"
        ):
            raise HTTPException(
                status_code=404,
                detail="공개된 콘텐츠를 찾을 수 없습니다.",
            )

        latest = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if latest != state:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            )

        return GameContentOverviewResponse(
            caseId=overview.case.case_id,
            title=overview.case.title,
            chapters=[
                ContentChapterResponse(
                    code=chapter.code,
                    order=chapter.order,
                    title=chapter.title,
                )
                for chapter in overview.chapters
                if chapter.code in state.unlocked_chapters
            ],
        )

    @app.get(
        "/api/games/{session_id}/content/scenes/{scene_id}",
        response_model=GameSceneResponse,
    )
    def get_game_scene(
        session_id: str,
        scene_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameSceneResponse:
        """게임 세션에 허용된 스토리 장면만 공개합니다."""

        # 반드시 Django 호출 이전에 게임 세션 소유권을 검증합니다.
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if re.fullmatch(r"SC-\d{4}", scene_id) is None:
            raise HTTPException(
                status_code=404,
                detail="스토리 장면을 찾을 수 없습니다.",
            )

        client = getattr(
            request.app.state,
            "django_content_client",
            None,
        )

        if not isinstance(client, DjangoContentClient):
            raise HTTPException(
                status_code=503,
                detail="콘텐츠 서비스를 사용할 수 없습니다.",
            )

        scene_release = None

        if scene_id == "SC-0402":
            approved_actions = getattr(
                request.app.state,
                "approved_investigation_actions",
                frozenset(),
            )

            acquired = {
                eid
                for eid, item in state.evidence.items()
                if item.stage in {"found", "resolved"}
            }

            if (
                state.phase != GamePhase.INVESTIGATION
                or state.outcome not in (None, "ONGOING")
                or state.current_chapter != "CH04"
                or "CH04" not in state.unlocked_chapters
                or not isinstance(approved_actions, frozenset)
                or "inspect-e29-a" not in approved_actions
                or not {"E26", "E28", "E29"}.issubset(acquired)
                or not {
                    "INF_POST_EVENT_DELETE",
                    "ACT_RECOVERED_AUDIO_VERIFIED",
                }.issubset(state.flags)
                or not can_access_e26_section_for_state(
                    "A",
                    state,
                    section_a_approved=getattr(
                        request.app.state,
                        "e26_section_a_approved",
                        False,
                    ),
                )
            ):
                raise HTTPException(404, "Scene unavailable")

            scene_release = getattr(
                request.app.state,
                "investigation_release_version",
                None,
            )

            if not isinstance(scene_release, str) or not scene_release:
                raise HTTPException(
                    503, "Content release unavailable"
                )

        if scene_id == "SC-0306":
            from crimescene.scenario.investigation_progress import InferenceRule

            approved_rules = getattr(
                request.app.state,
                "approved_inference_rules",
                (),
            )

            inference_approved = (
                isinstance(approved_rules, tuple)
                and any(
                    isinstance(rule, InferenceRule)
                    and rule.inference_id == "INF_POST_EVENT_DELETE"
                    and rule.chapter == "CH03"
                    and rule.evidence_ids == frozenset({"E20", "E26"})
                    and rule.required_flags == frozenset({
                        "ACT_AUDIT_LOG_ACCESS_VERIFIED"
                    })
                    for rule in approved_rules
                )
            )

            if (
                state.phase != GamePhase.INVESTIGATION
                or state.outcome not in (None, "ONGOING")
                or state.current_chapter != "CH03"
                or "CH03" not in state.unlocked_chapters
                or "INF_POST_EVENT_DELETE" not in state.flags
                or not inference_approved
                or not can_access_e26_section_for_state(
                    "A",
                    state,
                    section_a_approved=getattr(
                        request.app.state,
                        "e26_section_a_approved",
                        False,
                    ),
                )
            ):
                raise HTTPException(404, "Scene unavailable")

            scene_release = getattr(
                request.app.state,
                "investigation_release_version",
                None,
            )

            if not isinstance(scene_release, str) or not scene_release:
                raise HTTPException(503, "Content release unavailable")

        try:
            if scene_id in {"SC-0306", "SC-0402"}:
                scene = client.get_player_scene(
                    state.case_id,
                    scene_id,
                    investigation_release=scene_release,
                )
            else:
                scene = client.get_player_scene(
                    state.case_id,
                    scene_id,
                )
        except ContentServiceNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="스토리 장면을 찾을 수 없습니다.",
            ) from None
        except (ContentServiceError, ValueError):
            raise HTTPException(
                status_code=503,
                detail="스토리 장면을 조회할 수 없습니다.",
            ) from None

        # 현재 챕터이면서 해금된 장면만 공개합니다.
        if (
            scene.scene_id != scene_id
            or scene.chapter != state.current_chapter
            or scene.chapter not in state.unlocked_chapters
        ):
            raise HTTPException(
                status_code=404,
                detail="스토리 장면을 찾을 수 없습니다.",
            )

        # Django 조회 중 게임 상태 변경 여부를 검증합니다.
        latest = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if latest != state:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            )

        return GameSceneResponse(
            sceneId=scene.scene_id,
            chapter=scene.chapter,
            title=scene.title,
            sceneText=scene.scene_text,
        )

    # ========================================================
    # API 3. 프롤로그 완료
    # ========================================================

    @app.post(
        "/api/games/{session_id}/prologue/complete",
        response_model=GameResponse,
    )
    def complete_prologue(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameResponse:
        """프롤로그를 종료하고 조사 단계로 전환합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        # 종료된 게임은 진행할 수 없습니다.
        if state.outcome not in (None, "ONGOING"):
            raise HTTPException(
                status_code=409,
                detail="종료된 게임입니다.",
            )

        # 이미 조사 단계라면 중복 처리를 방지합니다.
        if state.phase == GamePhase.INVESTIGATION:
            return game_response(state)

        # 프롤로그 외 단계에서는 전환을 차단합니다.
        if state.phase != GamePhase.PROLOGUE:
            raise HTTPException(
                status_code=409,
                detail="프롤로그를 완료할 수 없는 상태입니다.",
            )

        # 기존 #27 진행 엔진 활용
        updated = transition_phase(
            state,
            GamePhase.INVESTIGATION,
        )

        # GameState와 NPC 세션 revision을 원자적으로 저장
        try:
            committed = repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            ) from None

        return game_response(
            committed,
            events=[
                {
                    "type": "PHASE_CHANGED",
                    "phase": "INVESTIGATION",
                }
            ],
        )

    # ========================================================
    # API 4. NPC 선택
    # ========================================================

    @app.post(
        "/api/games/{session_id}/characters/{character_id}/select",
        response_model=GameResponse,
    )
    def select_character(
        session_id: str,
        character_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> GameResponse:
        """해금된 NPC를 현재 조사 대상으로 선택합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        # 조사 단계에서만 NPC를 선택할 수 있습니다.
        if state.phase != GamePhase.INVESTIGATION:
            raise HTTPException(
                status_code=409,
                detail="조사 단계에서만 NPC를 선택할 수 있습니다.",
            )

        if state.outcome not in (None, "ONGOING"):
            raise HTTPException(
                status_code=409,
                detail="종료된 게임입니다.",
            )

        # NPC ID 검증
        if character_id not in EXPECTED_CHARACTER_IDS:
            raise HTTPException(
                status_code=422,
                detail="유효하지 않은 NPC입니다.",
            )

        # 서버 GameState 기준 해금 여부 검증
        if character_id not in state.unlocked_characters:
            raise HTTPException(
                status_code=403,
                detail="아직 해금되지 않은 NPC입니다.",
            )

        # GameState와 NPC 선택을 하나의 SQLite 트랜잭션으로 저장합니다.
        try:
            updated = repository.select_character_atomic(
                expected_state=state,
                character_id=character_id,
            )
        except (ValueError, PermissionError):
            raise HTTPException(
                status_code=409,
                detail="NPC 선택 중 게임 상태가 변경되었습니다.",
            ) from None

        return game_response(
            updated,
            events=[
                {
                    "type": "NPC_SELECTED",
                    "characterId": character_id,
                }
            ],
        )

    @app.get(
        "/api/games/{session_id}/chats/{character_id}",
        response_model=ChatHistoryResponse,
    )
    def get_chat_history(
        session_id: str,
        character_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> ChatHistoryResponse:
        """현재 플레이어에게 허용된 NPC 대화 기록만 조회합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.phase == GamePhase.PROLOGUE:
            raise HTTPException(
                status_code=409,
                detail="아직 조사가 시작되지 않았습니다.",
            )

        if character_id not in EXPECTED_CHARACTER_IDS:
            raise HTTPException(
                status_code=422,
                detail="유효하지 않은 NPC입니다.",
            )

        if character_id not in state.unlocked_characters:
            raise HTTPException(
                status_code=403,
                detail="아직 해금되지 않은 NPC입니다.",
            )

        # 조회 대상 세션은 서버가 소유권 검증을 완료한 세션입니다.
        history = repository.load_history(
            session_id,
            character_id,
        )

        return ChatHistoryResponse(
            sessionId=session_id,
            characterId=character_id,
            messages=[
                ChatMessageResponse(
                    userMessage=exchange.user_message,
                    displayText=render_stored_npc_message(
                        exchange.npc_message,
                        exchange.source_ids,
                    ),
                )
                for exchange in history
            ],
        )

    @app.post(
        "/api/games/{session_id}/chat",
        response_model=ChatResponse,
    )
    def chat_with_npc(
        session_id: str,
        body: ChatRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> ChatResponse:
        """기존 NPC 대화 엔진을 호출하고 검증된 결과만 반환합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.phase != GamePhase.INVESTIGATION or state.outcome not in (
            None,
            "ONGOING",
        ):
            raise HTTPException(
                status_code=409,
                detail="조사 단계에서만 대화할 수 있습니다.",
            )

        selection = repository.load_selection(session_id)

        if (
            selection is None
            or selection[1] != state.revision
            or selection[0] not in state.unlocked_characters
        ):
            raise HTTPException(
                status_code=409,
                detail="NPC 선택 상태가 올바르지 않습니다.",
            )

        if (
            state.content_version == "case001_v7_1"
            and body.presentedEvidenceId is not None
            and int(body.presentedEvidenceId[1:]) > 10
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid evidence ID for this version",
            )

        if (
            body.presentedEvidenceId is not None
            and body.presentedEvidenceId not in state.evidence
        ):
            raise HTTPException(
                status_code=403,
                detail="수집하지 않은 증거입니다.",
            )

        # 서버의 실제 RAG 리소스가 연결되지 않았다면 실행하지 않습니다.
        live_resources = getattr(
            request.app.state, "dialogue_resources", dialogue_resources
        )
        live_policies = getattr(
            request.app.state, "dialogue_policies", dialogue_policies
        )
        live_triggers = getattr(
            request.app.state, "dialogue_triggers", dialogue_triggers
        )
        live_flags = getattr(
            request.app.state, "dialogue_flag_config", dialogue_flag_config
        )

        if live_resources is None or live_policies is None:
            raise HTTPException(
                status_code=503,
                detail="NPC 대화 엔진이 준비되지 않았습니다.",
            )

        # 인증된 GameState를 기준으로 현재 NPC Agent만 실행합니다.
        # 증거 반응 처리는 Adapter가 한 번만 수행합니다.
        context = AgentContext.from_game_state(
            state,
            active_character_id=selection[0],
        )
        agent_request = AgentRequest(
            agent_type=AgentType.NPC,
            message=body.question,
            presented_evidence_id=body.presentedEvidenceId,
        )
        npc_agent = NPCAgent(
            repository=repository,
            resources=live_resources,
            policies=live_policies,
            trigger_rules=live_triggers,
            flag_config=live_flags,
            stage_events=stage_game_story_events,
            **(
                {
                    "npc_acquisition": (
                        request.app.state.published_npc_acquisition
                    )
                }
                if getattr(
                    request.app.state,
                    "published_npc_acquisition",
                    None,
                ) is not None
                else {}
            ),
            **(
                {
                    "presentation_stage_rules":
                    app.state.presentation_stage_rules,
                }
                if getattr(
                    app.state,
                    "presentation_stage_rules",
                    (),
                )
                else {}
            ),
            **(
                {
                    "reviewed_dialogue_bindings": getattr(
                        app.state,
                        "reviewed_dialogue_bindings",
                        (),
                    )
                }
                if getattr(
                    app.state,
                    "reviewed_dialogue_bindings",
                    (),
                )
                else {}
            ),
        )
        orchestrator = AgentOrchestrator(
            AgentRegistry([npc_agent]),
            load_state=repository.load_state,
            load_selection=repository.load_selection,
        )

        try:
            agent_result = orchestrator.execute(
                agent_request,
                context=context,
            )
            if not isinstance(agent_result, NPCAgentResult):
                raise TypeError("NPC Agent 결과 타입이 올바르지 않습니다.")

            # 기존 ChatResponse와 이벤트 생성 코드를 그대로 사용합니다.
            result = agent_result.dialogue

        except ContentServiceError:
            raise HTTPException(
                status_code=503,
                detail="스토리 이벤트 승인 정보를 확인할 수 없습니다.",
            ) from None

        except NPCEvidenceReactionError:
            raise HTTPException(
                status_code=422,
                detail="증거 데이터가 올바르지 않습니다.",
            ) from None

        except NPCDisplayError:
            raise HTTPException(
                status_code=502,
                detail="NPC 응답 형식이 올바르지 않습니다.",
            ) from None

        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail="현재 NPC 대화 또는 증거 제시가 허용되지 않습니다.",
            ) from None

        except LLMProviderError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
            ) from None

        except AgentExecutionTimeout:
            raise HTTPException(
                status_code=504,
                detail="NPC 대화 처리 시간이 초과됐습니다.",
            ) from None

        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="대화 처리 중 게임 상태가 변경되었습니다.",
            ) from None

        except RuntimeError as exc:
            # 실행 직전 상태 경쟁은 기존 API의 409 충돌 응답을 유지합니다.
            if str(exc) != "게임 상태 스냅샷이 최신 상태와 다릅니다.":
                raise
            raise HTTPException(
                status_code=409,
                detail="대화 처리 중 게임 상태가 변경되었습니다.",
            ) from None

        events = [
            {
                "type": "NPC_REPLIED",
                "characterId": result.turn.character_id,
            }
        ]

        if result.presentation_created:
            events.append(
                {
                    "type": "EVIDENCE_PRESENTED",
                    "evidenceId": body.presentedEvidenceId,
                }
            )

        if result.disclosed_card_ids:
            events.append({"type": "KNOWLEDGE_UPDATED"})

        if result.trigger_ids:
            events.append({"type": "GAME_PROGRESS_UPDATED"})

        if not result.turn.display_text.strip():
            raise HTTPException(
                status_code=502,
                detail="NPC 응답 형식이 올바르지 않습니다.",
            )

        return ChatResponse(
            characterId=result.turn.character_id,
            display_text=result.turn.display_text,
            game=game_response(
                result.state,
                events=events,
            ),
        )

    @app.post(
        "/api/games/{session_id}/evidence/E30/consent",
        response_model=GameResponse,
    )
    def submit_e30_consent(
        session_id: str,
        payload: E30ConsentRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> JSONResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        updated = grant_e30_player_consent(
            state,
            expected_revision=payload.expectedRevision,
            consent=payload.consent,
            approval_check=getattr(
                request.app.state,
                "e30_approval_check",
                None,
            ),
        )

        if updated != state:
            try:
                updated = repository.commit_state(
                    expected_state=state,
                    updated_state=updated,
                )
            except ValueError:
                raise HTTPException(
                    409,
                    "Game state changed",
                    headers={"Cache-Control": "private, no-store"},
                ) from None

        result = game_response(updated)

        return JSONResponse(
            content=result.model_dump(mode="json"),
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post(
        "/api/games/{session_id}/evidence/{evidence_id}/collect",
        response_model=EvidenceCollectResponse,
    )
    def collect_game_evidence(
        session_id: str,
        evidence_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> EvidenceCollectResponse:
        """서버의 획득 허용 정책을 통과한 증거만 원자적으로 수집합니다."""
        state = load_owned_request(session_id, request, case001_owner)

        if state.phase != GamePhase.INVESTIGATION or state.outcome not in (
            None,
            "ONGOING",
        ):
            raise HTTPException(
                status_code=409, detail="조사 단계에서만 증거를 수집할 수 있습니다."
            )

        # Only server-registered acquisition routes are accepted.
        approved_routes = getattr(
            request.app.state,
            "approved_acquisition_routes",
            {},
        ) or {}

        legacy_ids = {
            f"E{i:02d}" for i in range(1, 11)
        }

        if (
            evidence_id not in legacy_ids
            and evidence_id not in approved_routes
        ):
            raise HTTPException(status_code=422, detail="유효하지 않은 증거 ID입니다.")

        selection = repository.load_selection(session_id)
        if selection is None or selection[1] != state.revision:
            raise HTTPException(status_code=409, detail="NPC 선택 상태가 변경됐습니다.")
        active_npc = selection[0]
        if active_npc not in state.unlocked_characters:
            raise HTTPException(status_code=403, detail="해금되지 않은 NPC입니다.")

        resources = getattr(request.app.state, "dialogue_resources", None)
        flags = getattr(request.app.state, "dialogue_flag_config", None)
        policy_ids = getattr(request.app.state, "acquisition_policy_ids", None) or {}
        acquisition_evaluator = (
            getattr(request.app.state, "acquisition_evaluator", resources.evaluator)
            if resources is not None
            else None
        )

        # 획득 정책 또는 해금 규칙이 누락되면 절대로 증거를 지급하지 않습니다.
        if (
            resources is None
            or flags is None
            or not (policy_ids or approved_routes)
        ):
            raise HTTPException(
                status_code=503, detail="증거 수집 엔진이 준비되지 않았습니다."
            )

        if (
            evidence_id not in policy_ids
            and evidence_id not in approved_routes
        ):
            raise HTTPException(
                status_code=403, detail="이 증거의 수집 조건이 설정되지 않았습니다."
            )

        # Django 콘텐츠 정책이 활성화된 경우에만 추가 검증합니다.
        django_prerequisites: tuple[str, ...] = ()

        if evidence_id in approved_routes or getattr(
            request.app.state,
            "django_evidence_gate_enabled",
            False,
        ):
            client = getattr(
                request.app.state,
                "django_content_client",
                None,
            )

            if not isinstance(client, DjangoContentClient):
                raise HTTPException(
                    status_code=503,
                    detail="증거 공개 조건 검증 서비스를 사용할 수 없습니다.",
                )

            try:
                requirements = client.get_evidence_requirements(
                    state.case_id,
                    evidence_id,
                )
            except (ContentServiceError, ValueError):
                # Django 장애나 미승인 증거는 모두 수집을 차단합니다.
                raise HTTPException(
                    status_code=503,
                    detail="증거 공개 조건을 확인할 수 없습니다.",
                ) from None

            django_prerequisites = tuple(requirements.prerequisites)

        try:
            result = collect_evidence_atomic(
                session_id=session_id,
                evidence_id=evidence_id,
                active_character_id=active_npc,
                repository=repository,
                evidence_rules=resources.evidence_rules,
                acquisition_policy_ids=policy_ids,
                evaluator=acquisition_evaluator,
                unlock_rules=flags.npc_rules,
                django_prerequisites=django_prerequisites,
                stage_events=stage_game_story_events,
                approved_routes=approved_routes,
            )

        except ContentServiceError:
            raise HTTPException(
                status_code=503,
                detail="스토리 이벤트 승인 정보를 확인할 수 없습니다.",
            ) from None

        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail="증거 수집 조건을 충족하지 않았습니다.",
            ) from None

        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="증거 수집 중 게임 상태가 변경됐습니다.",
            ) from None

        events: list[dict[str, str]] = []
        if result.created:
            events.append({"type": "EVIDENCE_COLLECTED", "evidenceId": evidence_id})
            for npc_id in result.unlocked_npcs:
                events.append({"type": "NPC_UNLOCKED", "characterId": npc_id})

        return EvidenceCollectResponse(
            evidenceId=evidence_id,
            created=result.created,
            collectedCount=result.progress.collected_count,
            totalCount=result.progress.total_count,
            newlyUnlockedCharacters=list(result.unlocked_npcs),
            game=game_response(result.state, events=events),
        )

    def get_evidence_rules(request: Request):
        """서버에서 검증된 증거 규칙만 사용합니다."""
        resources = getattr(
            request.app.state,
            "dialogue_resources",
            dialogue_resources,
        )

        if resources is None or not resources.evidence_rules:
            raise HTTPException(
                status_code=503,
                detail="증거 데이터가 준비되지 않았습니다.",
            )

        return resources.evidence_rules

    # ========================================================
    # API: 증거 보관함 조회
    # ========================================================

    @app.get(
        "/api/games/{session_id}/evidence",
        response_model=EvidenceListResponse,
    )
    def get_evidence_list(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> EvidenceListResponse:

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        rules = get_evidence_rules(request)

        try:
            progress = get_collection_progress(state, rules)

            if state.score != progress.score:
                raise ValueError("증거 점수가 일치하지 않습니다.")

        except (ValueError, TypeError):
            raise HTTPException(
                status_code=409,
                detail="증거 데이터의 무결성이 일치하지 않습니다.",
            ) from None

        items = [
            EvidenceItemResponse(
                evidenceId=evidence_id,
                name=rules[evidence_id].name,
                score=rules[evidence_id].score,
                stage=evidence_state.stage,
            )
            for evidence_id, evidence_state in sorted(state.evidence.items())
        ]

        return EvidenceListResponse(
            items=items,
            collectedCount=progress.collected_count,
            totalCount=progress.total_count,
        )

    # ========================================================
    # ISSUE65_EVIDENCE_AVAILABLE_V1: only policy-eligible evidence is advertised.
    @app.get(
        "/api/games/{session_id}/evidence/available",
        response_model=EvidenceAvailableResponse,
    )
    def get_available_evidence(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> EvidenceAvailableResponse:
        state = load_owned_request(session_id, request, case001_owner)
        if state.phase != GamePhase.INVESTIGATION or state.outcome not in (
            None,
            "ONGOING",
        ):
            return EvidenceAvailableResponse(items=[])

        selection = repository.load_selection(session_id)
        if selection is None or selection[1] != state.revision:
            raise HTTPException(status_code=409, detail="NPC 선택 상태가 변경됐습니다.")
        active_npc = selection[0]
        if active_npc not in state.unlocked_characters:
            raise HTTPException(status_code=403, detail="해금되지 않은 NPC입니다.")

        resources = getattr(request.app.state, "dialogue_resources", dialogue_resources)
        policy_ids = getattr(request.app.state, "acquisition_policy_ids", None)
        evaluator = getattr(request.app.state, "acquisition_evaluator", None)
        if resources is None or not policy_ids or evaluator is None:
            raise HTTPException(
                status_code=503, detail="증거 수집 엔진이 준비되지 않았습니다."
            )

        items = []
        for evidence_id, policy_id in sorted(policy_ids.items()):
            rule = resources.evidence_rules.get(evidence_id)
            if (
                rule is None
                or rule.holder != active_npc
                or evidence_id in state.evidence
                or not evaluator.is_allowed(
                    policy_id, state, active_character_id=active_npc
                )
            ):
                continue
            # Only display evidence after the independent acquisition policy passes.
            items.append(
                EvidenceAvailableItemResponse(
                    evidenceId=evidence_id, name=rule.name, score=rule.score
                )
            )
        return EvidenceAvailableResponse(items=items)

    @app.get(
        "/api/games/{session_id}/evidence/{evidence_id}",
        response_model=EvidenceDetailResponse,
    )
    def get_collected_evidence_detail(
        session_id: str,
        evidence_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> EvidenceDetailResponse:
        state = load_owned_request(session_id, request, case001_owner)
        evidence_state = state.evidence.get(evidence_id)
        # 404 for unrevealed items: do not expose their existence or metadata.
        if evidence_state is None or evidence_state.stage not in {"found", "resolved"}:
            raise HTTPException(status_code=404, detail="증거를 찾을 수 없습니다.")
        rule = get_evidence_rules(request).get(evidence_id)
        if rule is None:
            raise HTTPException(
                status_code=409, detail="증거 데이터가 일치하지 않습니다."
            )
        resources = getattr(
            request.app.state,
            "dialogue_resources",
            dialogue_resources,
        )

        if evidence_id == "E30" or (
            evidence_id == "E26"
            and getattr(
                request.app.state,
                "e26_section_a_approved",
                False,
            ) is not True
        ):
            raise HTTPException(404, "Evidence unavailable")

        documents: list[EvidenceDocumentResponse] = []
        if (
            resources is not None
            and getattr(resources, "documents", None) is not None
            and getattr(resources, "evaluator", None) is not None
        ):
            # 공개 가능한 플레이어 문서만 기존 접근 정책으로 재검증합니다.
            authorized = {
                document.doc_id: document
                for document in select_authorized_player_documents(
                    resources.documents,
                    state,
                    resources.evaluator,
                )
            }
            collected = {
                item_id
                for item_id, item_state in state.evidence.items()
                if item_state.stage in {"found", "resolved"}
            }

            for document in resources.documents:
                if document.family != "evidence":
                    continue
                if document.access_scope != "collected_evidence":
                    continue
                if evidence_id not in document.source_evidence_ids:
                    continue
                # 연결된 다른 증거가 미수집이면 해당 문서 전체를 차단합니다.
                if not set(document.source_evidence_ids).issubset(collected):
                    continue

                approved = authorized.get(document.doc_id)
                if approved is None:
                    continue

                documents.append(
                    EvidenceDocumentResponse(
                        id=approved.doc_id,
                        label=f"문서 {len(documents) + 1}",
                        title=approved.title,
                        body=approved.content,
                    )
                )

        # 플레이어에게 이미 공개된 증거 문서 또는 증거 해금 조건과
        # 직접 연결된 관계만 공개합니다. 관리자 관계/미해금 NPC는 제외합니다.
        # Return only the independently authorized section A.
        if evidence_id == "E26":
            if (
                len(documents) != 1
                or documents[0].id != "DOC-1120-E26-A"
            ):
                raise HTTPException(404, "Evidence unavailable")

            return EvidenceDetailResponse(
                id=evidence_id,
                title=rule.name,
                body=documents[0].body,
                holderId=rule.holder,
                acquiredBy=None,
                confirmedRelations=[],
                documents=documents,
            )

        approved_doc_ids = {document.id for document in documents}
        visible_people = set(state.unlocked_characters) & set(EXPECTED_CHARACTER_IDS)
        visible_people.add("V01")  # 이미 공개된 피해자
        confirmed_relations: list[dict[str, str]] = []
        seen_relations: set[tuple[str, str]] = set()
        trusted_edges = (
            getattr(resources, "trusted_edges", ()) if resources is not None else ()
        )
        for edge in sorted(trusted_edges or (), key=lambda item: item.edge_id):
            if state.content_version == "case001_1120" and (
                {"E26", "E30"} & set(edge.required_evidence)
            ):
                continue

            # 증거를 가진 인물과 직접 연결된 관계만 표시합니다.
            if rule.holder not in {edge.source_id, edge.target_id}:
                continue
            other_id = (
                edge.target_id if edge.source_id == rule.holder else edge.source_id
            )
            if other_id not in visible_people:
                continue
            # 수집 또는 공개 승인된 문서와 직접 연관되지 않으면 제외합니다.
            if (
                evidence_id not in edge.required_evidence
                and not approved_doc_ids.intersection(edge.source_doc_ids)
            ):
                continue
            # 기존 Neo4j 관계 검색과 동일한 공개 정책 판정 함수를 사용합니다.
            if not is_relation_visible(edge, state):
                continue
            pair = (other_id, edge.relation)
            if pair in seen_relations:
                continue
            seen_relations.add(pair)
            confirmed_relations.append({"id": other_id, "label": edge.relation})

        return EvidenceDetailResponse(
            id=evidence_id,
            title=rule.name,
            body=documents[0].body if documents else None,
            holderId=rule.holder,
            acquiredBy=None,  # 획득 경로는 현재 GameState에 저장되지 않습니다.
            confirmedRelations=confirmed_relations,
            documents=documents,
        )

    # ========================================================
    # API: 획득한 증거 사진 조회
    # ========================================================

    @app.get(
        "/api/games/{session_id}/evidence/{evidence_id}/photo",
        response_class=FileResponse,
    )
    def get_evidence_photo(
        session_id: str,
        evidence_id: str,
        request: Request,
        thumbnail: bool = False,
        case001_owner: str | None = Cookie(default=None),
    ) -> FileResponse:
        """세션 소유자에게 획득한 증거 사진만 제공합니다."""

        # 기존 세션 소유권 검증 재사용
        state = load_owned_request(session_id, request, case001_owner)

        # 미획득 증거는 존재 여부까지 숨깁니다.
        evidence_state = state.evidence.get(evidence_id)
        if evidence_state is None or evidence_state.stage not in {"found", "resolved"}:
            raise HTTPException(
                status_code=404,
                detail="증거를 찾을 수 없습니다.",
            )

        # 이미지 디렉터리는 환경변수로 설정합니다.
        # Protected images require independent approval.
        if evidence_id in {"E26", "E30"}:
            raise HTTPException(404, "Evidence image unavailable")

        image_dir_raw = os.getenv(
            "CRIMESCENE_EVIDENCE_IMAGE_DIR",
            ".local/case001_photos",
        )

        image_dir = Path(image_dir_raw).expanduser()
        if not image_dir.is_absolute():
            backend_root = Path(__file__).resolve().parents[3]
            image_dir = backend_root / image_dir

        image_dir = image_dir.resolve()

        # 별도 썸네일이 없다면 원본을 반환합니다.
        stems = (f"{evidence_id}_thumb", evidence_id) if thumbnail else (evidence_id,)

        extensions = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

        for stem in stems:
            for extension, media_type in extensions.items():
                image_path = (image_dir / f"{stem}{extension}").resolve()

                # 이미지 디렉터리 밖의 파일 접근 방지
                if not image_path.is_relative_to(image_dir):
                    continue

                if image_path.is_file():
                    return FileResponse(
                        path=image_path,
                        media_type=media_type,
                        headers={
                            "Cache-Control": "private, no-store",
                            "X-Content-Type-Options": "nosniff",
                        },
                    )

        raise HTTPException(
            status_code=404,
            detail="증거 이미지 파일이 없습니다.",
        )

    # API: 게임 진행률 조회
    # ========================================================

    @app.get(
        "/api/games/{session_id}/progress",
        response_model=ProgressResponse,
    )
    def get_game_progress(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> ProgressResponse:

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        rules = get_evidence_rules(request)

        try:
            progress = get_collection_progress(state, rules)
            accusation_allowed = can_accuse(state, rules)

        except (ValueError, TypeError):
            raise HTTPException(
                status_code=409,
                detail="게임 진행 데이터의 무결성이 일치하지 않습니다.",
            ) from None

        rate = (
            progress.collected_count / progress.total_count * 100
            if progress.total_count
            else 0.0
        )

        return ProgressResponse(
            collection=CollectionResponse(
                score=progress.score,
                total=progress.total,
            ),
            collectedCount=progress.collected_count,
            totalCount=progress.total_count,
            collectionRate=round(rate, 2),
            canAccuse=accusation_allowed,
            attemptsLeft=state.attempts_left,
        )

    @app.get(
        "/api/games/{session_id}/relationships",
        response_model=RelationshipResponse,
    )
    def get_relationships(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> RelationshipResponse:
        """현재 플레이어에게 공개된 인물 관계만 반환합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.phase == GamePhase.PROLOGUE:
            raise HTTPException(
                status_code=409,
                detail="아직 조사가 시작되지 않았습니다.",
            )

        resources = getattr(
            request.app.state,
            "dialogue_resources",
            dialogue_resources,
        )

        if resources is None:
            raise HTTPException(
                status_code=503,
                detail="관계도 데이터가 준비되지 않았습니다.",
            )

        # 해금된 NPC와 공개 인물 V01만 표시합니다.
        visible_ids = (set(state.unlocked_characters) & set(EXPECTED_CHARACTER_IDS)) | {
            "V01"
        }

        labels = {
            entity["entity_id"]: entity["label"]
            for entity in resources.registry
            if (
                isinstance(entity, dict)
                and entity.get("case_id") == state.case_id
                and entity.get("entity_id") in visible_ids
                and isinstance(entity.get("label"), str)
            )
        }

        nodes = [
            RelationshipNodeResponse(
                id=entity_id,
                label=labels.get(entity_id, entity_id),
            )
            for entity_id in sorted(visible_ids)
        ]

        edges: dict[str, RelationshipEdgeResponse] = {}

        try:
            for character_id in sorted(visible_ids & set(EXPECTED_CHARACTER_IDS)):
                relations = search_character_relations(
                    resources.neo4j_driver,
                    character_id,
                    state,
                    resources.trusted_edges,
                    top_k=100,
                )

                for relation in relations:
                    # 관계의 양 끝이 공개된 인물인지 재확인합니다.
                    if (
                        relation.source_id not in visible_ids
                        or relation.target_id not in visible_ids
                    ):
                        continue

                    edges[relation.edge_id] = RelationshipEdgeResponse(
                        id=relation.edge_id,
                        sourceId=relation.source_id,
                        targetId=relation.target_id,
                        relation=relation.relation,
                    )

        except (Neo4jError, ServiceUnavailable, SessionExpired):
            raise HTTPException(
                status_code=503,
                detail="관계도 조회 서비스에 연결할 수 없습니다.",
            ) from None

        return RelationshipResponse(
            nodes=nodes,
            edges=[edges[edge_id] for edge_id in sorted(edges)],
        )

    @app.post(
        "/api/games/{session_id}/accusations",
        response_model=AccusationResponse,
    )
    def accuse_suspect(
        session_id: str,
        body: AccusationRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> AccusationResponse:
        """서버에서 지목 조건을 검증하고 결과를 저장합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if body.expectedRevision != state.revision:
            raise HTTPException(
                status_code=409,
                detail="게임 상태가 변경되었습니다.",
            )

        if state.phase not in (
            GamePhase.INVESTIGATION,
            GamePhase.ACCUSATION,
        ) or state.outcome not in (None, "ONGOING"):
            raise HTTPException(
                status_code=409,
                detail="현재 범인을 지목할 수 없습니다.",
            )

        if body.suspectId not in state.unlocked_characters:
            raise HTTPException(
                status_code=403,
                detail="아직 해금되지 않은 NPC입니다.",
            )

        rules = get_evidence_rules(request)

        try:
            allowed = can_accuse(state, rules)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=409,
                detail="게임 진행 데이터가 올바르지 않습니다.",
            ) from None

        # 증거가 부족하면 DB와 지목 기회를 변경하지 않습니다.
        if not allowed:
            return AccusationResponse(
                result=AccusationStatus.NOT_ENOUGH_EVIDENCE,
                attemptsLeft=state.attempts_left,
                game=game_response(state),
            )

        # 실제 범인 정보는 서버 전용 데이터만 사용합니다.
        truth = getattr(request.app.state, "case_truth", None)

        if not isinstance(truth, CaseTruth):
            raise HTTPException(
                status_code=503,
                detail="범인 판정 엔진이 준비되지 않았습니다.",
            )

        try:
            result = submit_accusation_request_atomic(
                session_id=session_id,
                suspect_id=body.suspectId,
                expected_revision=body.expectedRevision,
                repository=repository,
                truth=truth,
                evidence_rules=rules,
            )

        except (PermissionError, ValueError):
            raise HTTPException(
                status_code=409,
                detail="지목 처리 중 게임 상태가 변경되었습니다.",
            ) from None

        return AccusationResponse(
            result=result.status,
            attemptsLeft=result.attempts_left,
            game=game_response(
                result.state,
                events=[{"type": "ACCUSATION_RESULT"}],
            ),
        )

    # ========================================================
    # API: 게임 엔딩 조회
    # ========================================================

    def load_owned_ending_image_state(
        session_id: str,
        request: Request,
        cookie: str | None,
    ) -> GameState:
        try:
            return load_owned_request(session_id, request, cookie)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
                headers={
                    **(exc.headers or {}),
                    **IMAGE_HEADERS,
                },
            ) from exc

    @app.get(
        "/api/games/{session_id}/ending/images",
        response_model=EndingImagesResponse,
    )
    def get_ending_images(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> JSONResponse:
        state = load_owned_ending_image_state(
            session_id,
            request,
            case001_owner,
        )

        result = build_ending_images_response(state)

        return JSONResponse(
            content=result.model_dump(mode="json"),
            headers=dict(IMAGE_HEADERS),
        )

    @app.get(
        "/api/games/{session_id}/ending/images/{image_index}",
        response_class=FileResponse,
    )
    def get_ending_image(
        session_id: str,
        image_index: int,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> FileResponse:
        state = load_owned_ending_image_state(
            session_id,
            request,
            case001_owner,
        )

        path = resolve_ending_image(state, image_index)

        return FileResponse(
            path=path,
            media_type="image/png",
            headers=dict(IMAGE_HEADERS),
        )

    @app.get(
        "/api/games/{session_id}/ending",
        response_model=EndingResponse,
    )
    def get_ending(
        session_id: str,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> EndingResponse:
        """게임이 종료된 경우에만 엔딩을 공개합니다."""

        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        # 게임 종료 전 엔딩 정보 접근 차단
        if state.content_version == "case001_1120":
            from crimescene.scenario.expanded_ending import (
                ExpandedCaseTruth,
            )

            code = state.ending_code

            if state.phase != GamePhase.FINISHED or code is None:
                raise HTTPException(
                    409, "Ending unavailable"
                )

            titles = {
                "NO_EVIDENCE": "\uc99d\uac70 \ubd80\uc871",
                "UNSOLVED": "\uc218\uc0ac \uc2e4\ud328",
                "ESTIMATED": "\ucd94\uc815 \uc131\ub9bd",
                "FULL": "\uc0ac\uac74 \ud574\uacb0",
                "DEEP": "\uc2ec\ud654 \uc5d4\ub529",
            }

            public_truth = None

            if code in {"FULL", "DEEP"}:
                truth = getattr(
                    request.app.state,
                    "case_truth",
                    None,
                )

                if (
                    not isinstance(truth, ExpandedCaseTruth)
                    or truth.case_id != state.case_id
                ):
                    raise HTTPException(
                        503, "Ending unavailable"
                    )

                public_truth = EndingTruthResponse(
                    perpetratorId=truth.perpetrator_character_id,
                    motive=truth.motive,
                    causeOfDeath=truth.cause_of_death,
                    crimeMethod=truth.crime_method,
                )

            return EndingResponse(
                outcome=code,
                title=titles[code],
                message=titles[code],
                deepEligible=code == "DEEP",
                truth=public_truth,
                game=game_response(state),
            )

        if state.phase != GamePhase.FINISHED or state.outcome not in (
            "SUCCESS",
            "FAILURE",
        ):
            raise HTTPException(
                status_code=409,
                detail="게임이 종료된 후 엔딩을 확인할 수 있습니다.",
            )

        # 범인 지목 성공
        if state.outcome == "SUCCESS":
            truth = getattr(
                request.app.state,
                "case_truth",
                None,
            )

            if not isinstance(truth, CaseTruth) or truth.case_id != state.case_id:
                raise HTTPException(
                    status_code=503,
                    detail="엔딩 데이터를 불러올 수 없습니다.",
                )

            return EndingResponse(
                outcome="SUCCESS",
                title="사건 해결",
                message="수집한 증거와 진술을 통해 사건의 진실을 밝혀냈습니다.",
                deepEligible=state.deep_eligible,
                truth=EndingTruthResponse(
                    perpetratorId=truth.perpetrator_character_id,
                    motive=truth.motive,
                    causeOfDeath=truth.cause_of_death,
                    crimeMethod=truth.crime_method,
                ),
                game=game_response(state),
            )

        # 범인 지목 실패
        return EndingResponse(
            outcome="FAILURE",
            title="미해결 사건",
            message="범인 지목 기회를 모두 사용했습니다. 사건은 미해결로 남았습니다.",
            deepEligible=False,
            truth=None,
            game=game_response(state),
        )

    # Issue #120: owner-scoped story event delivery.
    from crimescene.api.story_event_http import (
        create_story_event_router,
    )

    app.include_router(
        create_story_event_router(
            repository=repository,
            load_owned_request=load_owned_request,
        )
    )

    app.include_router(
        create_agent_router(
            repository=repository,
            load_owned_request=load_owned_request,
            dialogue_resources=dialogue_resources,
        )
    )

    from crimescene.api.investigation_http import (
        create_investigation_router,
    )

    app.include_router(
        create_investigation_router(
            repository=repository,
            load_owned_request=load_owned_request,
            stage_events=stage_game_story_events,
        )
    )

    from crimescene.api.inference_http import (
        create_inference_router,
    )

    app.include_router(
        create_inference_router(
            repository=repository,
            load_owned_request=load_owned_request,
            stage_events=stage_game_story_events,
        )
    )

    from crimescene.api.expanded_ending_http import (
        create_expanded_ending_router,
    )

    app.include_router(
        create_expanded_ending_router(
            repository=repository,
            load_owned_request=load_owned_request,
            stage_events=stage_game_story_events,
        )
    )

    return app
