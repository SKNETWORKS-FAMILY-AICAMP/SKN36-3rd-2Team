"""Issue #165 - owner-scoped objective and inference API."""

from collections.abc import Callable
from types import MappingProxyType

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from crimescene.api.django_content_client import (
    ContentServiceError,
)
from crimescene.scenario.investigation_progress import (
    InferenceRule,
    ObjectiveRule,
    objective_status,
    submit_inference,
)
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


# Issue #213: 플레이어에게 공개할 수 있는 목표 문구만 관리한다.
# 원본 힌트, 증거 ID 및 내부 완료 조건은 반환하지 않는다.
OBJECTIVE_DISPLAY_TEXT = MappingProxyType({
    "OBJ_FIND_STUDENT_RECORD": (
        "학생 기록 조사",
        "사진에서 지워진 이름과 관련된 학생 기록을 확인하세요.",
    ),
    "OBJ_CHECK_SCHOLARSHIP": (
        "장학금 기록 대조",
        "확보한 회람 자료를 장학금 수령 기록과 비교하세요.",
    ),
    "OBJ_CHECK_SIGNOFF": (
        "학적 변경 승인 확인",
        "관련 승인 기록의 서명과 날짜를 확인하세요.",
    ),
    "OBJ_TALK_SEOMIRAN": (
        "학적 변경 경위 조사",
        "서미란에게 2016년 학적 변경 경위를 질문하세요.",
    ),
    "OBJ_CHECK_2016_VIDEO": (
        "과거 영상 자료 조사",
        "2016년 행사 당시의 촬영 자료를 확인하세요.",
    ),
    "OBJ_VERIFY_DEPARTURE": (
        "당시 이탈 경위 조사",
        "확보한 자료를 토대로 이후의 이동 경위를 확인하세요.",
    ),
    "OBJ_CHECK_DRAFT_EMAIL": (
        "신기범의 일정 확인",
        "신기범이 남긴 일정과 메일 관련 자료를 조사하세요.",
    ),
    "OBJ_FIND_CARD_USER": (
        "임시 카드 사용자 조사",
        "카드 사용 기록과 다른 자료를 비교해 사용자를 좁혀 보세요.",
    ),
    "OBJ_FIND_SHUTDOWN_REASON": (
        "CCTV 중단 원인 조사",
        "CCTV가 중단된 이유를 관련 기록을 통해 확인하세요.",
    ),
    "OBJ_RECONSTRUCT_ROUTE": (
        "사건 당시 동선 재구성",
        "계단 주변의 이동 시각과 경로를 비교하세요.",
    ),
    "OBJ_CHECK_REFLECTION": (
        "사진 속 인물 조사",
        "사진에 비친 인물의 알리바이를 확인하세요.",
    ),
})

DEFAULT_OBJECTIVE_DISPLAY = (
    "수사 목표",
    "현재 공개된 자료와 인물을 조사하세요.",
)


class InferenceRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    evidenceIds: list[str] = Field(
        min_length=2,
        max_length=3,
    )

    expectedRevision: int = Field(ge=0)


class InferenceResponse(BaseModel):
    accepted: bool
    created: bool
    inferenceIds: list[str]
    revision: int


class ObjectiveItem(BaseModel):
    objectiveId: str
    status: str
    chapter: str
    title: str
    description: str


class ObjectiveResponse(BaseModel):
    items: list[ObjectiveItem]


def create_inference_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: Callable,
    stage_events: Callable[[GameState], GameState],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/games/{session_id}/objectives",
        response_model=ObjectiveResponse,
    )
    def list_objectives(
        session_id: str,
        request: Request,
        response: Response,
        case001_owner: str | None = Cookie(default=None),
    ) -> ObjectiveResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        rules = getattr(
            request.app.state,
            "approved_objective_rules",
            (),
        )

        if (
            not isinstance(rules, tuple)
            or any(
                not isinstance(rule, ObjectiveRule)
                for rule in rules
            )
        ):
            raise HTTPException(503, "Objectives unavailable")

        items = []

        for rule in rules:
            status = objective_status(state, rule)

            if status == "LOCKED":
                continue

            title, description = OBJECTIVE_DISPLAY_TEXT.get(
                rule.objective_id,
                DEFAULT_OBJECTIVE_DISPLAY,
            )

            items.append(
                ObjectiveItem(
                    objectiveId=rule.objective_id,
                    status=status,
                    chapter=rule.chapter,
                    title=title,
                    description=description,
                )
            )

        response.headers["Cache-Control"] = "private, no-store"

        return ObjectiveResponse(items=items)

    @router.post(
        "/api/games/{session_id}/inferences",
        response_model=InferenceResponse,
    )
    def infer(
        session_id: str,
        body: InferenceRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> InferenceResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        ids = frozenset(body.evidenceIds)

        if len(ids) != len(body.evidenceIds):
            raise HTTPException(422, "Duplicate evidence ID")

        rules = getattr(
            request.app.state,
            "approved_inference_rules",
            (),
        )

        if (
            not isinstance(rules, tuple)
            or any(
                not isinstance(rule, InferenceRule)
                for rule in rules
            )
        ):
            raise HTTPException(503, "Inference unavailable")

        try:
            result = submit_inference(
                state,
                evidence_ids=ids,
                rules=rules,
                **(
                    {
                        "e26_section_a_approved": getattr(
                            request.app.state,
                            "e26_section_a_approved",
                            False,
                        )
                    }
                    if "E26" in ids
                    else {}
                ),
            )

        except PermissionError:
            raise HTTPException(403, "Inference denied") from None

        except (TypeError, ValueError):
            raise HTTPException(422, "Invalid inference") from None

        committed = state

        try:
            if result.created:
                updated = stage_events(result.state)

                committed = repository.commit_state(
                    expected_state=state,
                    updated_state=updated,
                )

            elif repository.load_state(session_id) != state:
                raise ValueError("Game state changed")

        except ContentServiceError:
            raise HTTPException(
                503, "Story approval unavailable"
            ) from None

        except ValueError:
            raise HTTPException(
                409, "Game state changed"
            ) from None

        return InferenceResponse(
            accepted=result.accepted,
            created=result.created,
            inferenceIds=list(result.inference_ids),
            revision=committed.revision,
        )

    return router
