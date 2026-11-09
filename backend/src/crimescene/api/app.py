"""Issue #62 - 게임 시작, 저장, 이어하기 및 NPC 선택 API."""

import hashlib
import hmac
import secrets

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.game_progress import (
    create_initial_state,
    meets_accusation_requirements,
    transition_phase,
)
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

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


# ============================================================
# FastAPI Application Factory
# ============================================================


def create_app(
    repository: SQLiteCase001Repository,
    *,
    session_secret: str,
    secure_cookie: bool = False,
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

    return app
