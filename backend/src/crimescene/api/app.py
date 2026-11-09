"""Issue #62 - 게임 시작, 저장, 이어하기 및 NPC 선택 API."""

import hashlib
import hmac
import secrets
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from pydantic import BaseModel, ConfigDict, Field, field_validator

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import MAX_MESSAGE_LENGTH
from crimescene.retriever.graph_search import search_character_relations
from crimescene.scenario.accusation import AccusationStatus, can_accuse
from crimescene.scenario.accusation_service import (
    submit_accusation_request_atomic,
)
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.evidence_service import collect_evidence_atomic
from crimescene.scenario.game_progress import (
    create_initial_state,
    meets_accusation_requirements,
    transition_phase,
)
from crimescene.scenario.loaders.unlock_graph_loader import Case001UnlockRules
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
    run_case001_npc_dialogue_atomic,
)
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

    activeCharacterId: str
    unlockedCharacters: list[str]

    collection: CollectionResponse
    canAccuse: bool

    attemptsLeft: int
    outcome: str | None

    revision: int
    events: list[dict[str, str]]


class ChatRequest(BaseModel):
    """플레이어의 NPC 대화 요청."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        max_length=MAX_MESSAGE_LENGTH,
    )
    presentedEvidenceId: str | None = Field(
        default=None,
        pattern=r"^E(?:0[1-9]|10)$",
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

    # --------------------------------------------------------
    # 6. 공통 게임 응답 생성
    # --------------------------------------------------------

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
        can_accuse = (
            state.phase
            in (
                GamePhase.INVESTIGATION,
                GamePhase.ACCUSATION,
            )
            and state.outcome in (None, "ONGOING")
            and state.attempts_left > 0
            and meets_accusation_requirements(state)
        )

        return GameResponse(
            sessionId=state.session_id,
            phase=state.phase,
            activeCharacterId=active_npc,
            unlockedCharacters=list(state.unlocked_characters),
            collection=CollectionResponse(
                score=state.score,
                total=TOTAL_SCORE,
            ),
            canAccuse=can_accuse,
            attemptsLeft=state.attempts_left,
            outcome=state.outcome,
            revision=state.revision,
            events=events if events is not None else [],
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
                    displayText=exchange.npc_message,
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

        try:
            result = run_case001_npc_dialogue_atomic(
                body.question,
                session_id=session_id,
                repository=repository,
                resources=live_resources,
                policies=dict(live_policies),
                trigger_rules=live_triggers,
                presented_evidence_id=body.presentedEvidenceId,
                flag_config=live_flags,
            )

        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail="현재 NPC 대화 또는 증거 제시가 허용되지 않습니다.",
            ) from None

        except ValueError:
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

        # 명시적인 E01~E10만 허용합니다. 내부 규칙 및 관리자 정보는 반환하지 않습니다.
        if evidence_id not in {f"E{i:02d}" for i in range(1, 11)}:
            raise HTTPException(status_code=422, detail="유효하지 않은 증거 ID입니다.")

        selection = repository.load_selection(session_id)
        if selection is None or selection[1] != state.revision:
            raise HTTPException(status_code=409, detail="NPC 선택 상태가 변경됐습니다.")
        active_npc = selection[0]
        if active_npc not in state.unlocked_characters:
            raise HTTPException(status_code=403, detail="해금되지 않은 NPC입니다.")

        resources = getattr(request.app.state, "dialogue_resources", None)
        flags = getattr(request.app.state, "dialogue_flag_config", None)
        policy_ids = getattr(request.app.state, "acquisition_policy_ids", None)
        acquisition_evaluator = (
            getattr(request.app.state, "acquisition_evaluator", resources.evaluator)
            if resources is not None
            else None
        )

        # 획득 정책 또는 해금 규칙이 누락되면 절대로 증거를 지급하지 않습니다.
        if resources is None or flags is None or not policy_ids:
            raise HTTPException(
                status_code=503, detail="증거 수집 엔진이 준비되지 않았습니다."
            )

        if evidence_id not in policy_ids:
            raise HTTPException(
                status_code=403, detail="이 증거의 수집 조건이 설정되지 않았습니다."
            )

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
            )
        except PermissionError:
            raise HTTPException(
                status_code=403, detail="증거 수집 조건을 충족하지 않았습니다."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="증거 수집 중 게임 상태가 변경됐습니다."
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

    return app
