"""Issue #165 - server-verified investigation actions."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fastapi import APIRouter, Cookie, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from crimescene.api.django_content_client import (
    ContentServiceError,
    ContentServiceNotFoundError,
    DjangoContentClient,
)
from crimescene.scenario.acquisition_policy import (
    AcquisitionPolicy,
    allows_acquisition,
)
from crimescene.scenario.evidence_collection import (
    collect_evidence,
    get_collection_progress,
)
from crimescene.scenario.e26_section_policy import (
    can_acquire_e26_a,
    can_access_e26_section_for_state,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import (
    GamePhase,
    GameState,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@dataclass(frozen=True, slots=True)
class InvestigationAction:
    scene_id: str
    chapter: str
    evidence_id: str
    action_flag: str
    route_ids: frozenset[str]
    required_evidence: frozenset[str] = frozenset()
    any_evidence: frozenset[str] = frozenset()
    required_character: str | None = None
    required_flags: frozenset[str] = frozenset()


ACTION_CANDIDATES = {
    "inspect-e27-a": InvestigationAction(
        scene_id="SC-0306",
        chapter="CH03",
        evidence_id="E27",
        action_flag="ACT_ACCOUNTING_VERSIONS_COMPARED",
        route_ids=frozenset({"E27-A"}),
        required_evidence=frozenset({"E17", "E26"}),
        required_flags=frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        }),
    ),
    "inspect-e29-a": InvestigationAction(
        scene_id="SC-0402",
        chapter="CH04",
        evidence_id="E29",
        action_flag="ACT_RECOVERED_AUDIO_VERIFIED",
        route_ids=frozenset({"E29-A"}),
        required_evidence=frozenset({"E26", "E28"}),
        required_flags=frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        }),
    ),
    "inspect-e26-a": InvestigationAction(
        scene_id="SC-0306",
        chapter="CH03",
        evidence_id="E26",
        action_flag="ACT_AUDIT_LOG_ACCESS_VERIFIED",
        route_ids=frozenset({"E26-A"}),
        required_evidence=frozenset({"E20"}),
        required_character=None,
        required_flags=frozenset(),
    ),
    "inspect-sensor-record": InvestigationAction(
        scene_id="SC-0308",
        chapter="CH03",
        evidence_id="E23",
        action_flag="ACT_SENSOR_RECORD_INSPECTED",
        route_ids=frozenset({"E23-A", "E23-B"}),
        any_evidence=frozenset({"E21", "E22"}),
    ),
    "inspect-emergency-door-record": InvestigationAction(
        scene_id="SC-0309",
        chapter="CH03",
        evidence_id="E25",
        action_flag="ACT_EMERGENCY_DOOR_RECORD_INSPECTED",
        route_ids=frozenset({"E25-A"}),
        required_evidence=frozenset({"E23"}),
    ),
    "inspect-e11-a": InvestigationAction(
        scene_id="SC-0104",
        chapter="CH01",
        evidence_id="E11",
        action_flag="ACT_PHOTO_ORIGINAL_VERIFIED",
        route_ids=frozenset(["E11-A"]),
        required_evidence=frozenset([]),
    ),
    "inspect-e12-a": InvestigationAction(
        scene_id="SC-0201",
        chapter="CH02",
        evidence_id="E12",
        action_flag="ACT_STUDENT_RECORD_INSPECTED",
        route_ids=frozenset(["E12-A"]),
        required_evidence=frozenset(["E11"]),
    ),
    "inspect-e14-a": InvestigationAction(
        scene_id="SC-0203",
        chapter="CH02",
        evidence_id="E14",
        action_flag="ACT_ACADEMIC_RECORD_INSPECTED",
        route_ids=frozenset(["E14-A"]),
        required_evidence=frozenset(["E13"]),
    ),
    "inspect-e19-a": InvestigationAction(
        scene_id="SC-0102",
        chapter="CH01",
        evidence_id="E19",
        action_flag="ACT_RECEPTION_RECORD_INSPECTED",
        route_ids=frozenset(["E19-A"]),
        required_evidence=frozenset([]),
    ),
    "inspect-e20-a": InvestigationAction(
        scene_id="SC-0103",
        chapter="CH01",
        evidence_id="E20",
        action_flag="ACT_OFFICE_DATA_ACCESSED",
        route_ids=frozenset(["E20-A"]),
        required_evidence=frozenset(["E19"]),
    ),
    "inspect-e21-a": InvestigationAction(
        scene_id="SC-0302",
        chapter="CH03",
        evidence_id="E21",
        action_flag="ACT_CARD_OPERATION_VERIFIED",
        route_ids=frozenset(["E21-A"]),
        required_evidence=frozenset([]),
    ),
    "inspect-e24-a": InvestigationAction(
        scene_id="SC-0304",
        chapter="CH03",
        evidence_id="E24",
        action_flag="ACT_REFLECTION_ORIGINAL_VERIFIED",
        route_ids=frozenset(["E24-A"]),
        required_evidence=frozenset(["E23"]),
    ),
    "inspect-e12-b": InvestigationAction(
        scene_id="SC-0201",
        chapter="CH02",
        evidence_id="E12",
        action_flag="ACT_C07_STATEMENT_VERIFIED",
        route_ids=frozenset(["E12-B"]),
        required_evidence=frozenset([]),
        required_character="C07",
        required_flags=frozenset([]),
    ),
    "inspect-e13-a": InvestigationAction(
        scene_id="SC-0201",
        chapter="CH02",
        evidence_id="E13",
        action_flag="ACT_FOUNDATION_RECORD_ACCESSED",
        route_ids=frozenset(["E13-A"]),
        required_evidence=frozenset(["E12"]),
        required_character=None,
        required_flags=frozenset([]),
    ),
    "inspect-e14-b": InvestigationAction(
        scene_id="SC-0203",
        chapter="CH02",
        evidence_id="E14",
        action_flag="ACT_C08_STATEMENT_VERIFIED",
        route_ids=frozenset(["E14-B"]),
        required_evidence=frozenset([]),
        required_character="C08",
        required_flags=frozenset([]),
    ),
    "inspect-e15-a": InvestigationAction(
        scene_id="SC-0204",
        chapter="CH02",
        evidence_id="E15",
        action_flag="ACT_C05_INTERVIEW_COMPLETED",
        route_ids=frozenset(["E15-A"]),
        required_evidence=frozenset(["E14"]),
        required_character="C05",
        required_flags=frozenset([]),
    ),
    "inspect-e16-a": InvestigationAction(
        scene_id="SC-0205",
        chapter="CH02",
        evidence_id="E16",
        action_flag="ACT_C09_VIDEO_ORIGINAL_VERIFIED",
        route_ids=frozenset(["E16-A"]),
        required_evidence=frozenset(["E11", "E15"]),
        required_character="C09",
        required_flags=frozenset([]),
    ),
    "inspect-e17-a": InvestigationAction(
        scene_id="SC-0202",
        chapter="CH02",
        evidence_id="E17",
        action_flag="ACT_ACCOUNTING_ACCESS_VERIFIED",
        route_ids=frozenset(["E17-A"]),
        required_evidence=frozenset(["E12", "E13"]),
        required_character=None,
        required_flags=frozenset(["ACT_FUND_GAP_PUZZLE_VERIFIED"]),
    ),
    "inspect-e18-a": InvestigationAction(
        scene_id="SC-0205",
        chapter="CH02",
        evidence_id="E18",
        action_flag="ACT_POSTAL_RECORD_INSPECTED",
        route_ids=frozenset(["E18-A"]),
        required_evidence=frozenset(["E14", "E16"]),
        required_character=None,
        required_flags=frozenset([]),
    ),
    "inspect-e22-a": InvestigationAction(
        scene_id="SC-0303",
        chapter="CH03",
        evidence_id="E22",
        action_flag="ACT_C04_SECURITY_QUESTION_VERIFIED",
        route_ids=frozenset(["E22-A"]),
        required_evidence=frozenset([]),
        required_character="C04",
        required_flags=frozenset([]),
    ),
    "inspect-e25-b": InvestigationAction(
        scene_id="SC-0309",
        chapter="CH03",
        evidence_id="E25",
        action_flag="ACT_SECURITY_RECORD_ACCESS_VERIFIED",
        route_ids=frozenset(["E25-B"]),
        required_evidence=frozenset([]),
        required_character=None,
        required_flags=frozenset([]),
    ),
    "inspect-e28-a": InvestigationAction(
        scene_id="SC-0305",
        chapter="CH03",
        evidence_id="E28",
        action_flag="ACT_C06_ALIBI_INTERVIEW_COMPLETED",
        route_ids=frozenset(["E28-A"]),
        required_evidence=frozenset(["E24", "E25"]),
        required_character="C06",
        required_flags=frozenset([]),
    ),
}


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expectedRevision: int = Field(ge=0)


class InvestigationResponse(BaseModel):
    evidenceId: str
    created: bool
    score: int
    total: int
    revision: int


class SceneCompletionResponse(BaseModel):
    sceneId: str
    created: bool
    characterId: str
    presentedEvidenceId: str
    dialogue: list[str]
    revision: int


class LegacyInspectionRequest(InvestigationRequest):
    presentedEvidenceId: str | None = None
    presentedEvidenceIds: list[str] | None = None


def create_investigation_router(
    *,
    repository: SQLiteCase001Repository,
    load_owned_request: Callable,
    stage_events: Callable[[GameState], GameState],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/games/{session_id}/investigations/{action_id}",
        response_model=InvestigationResponse,
    )
    def investigate(
        session_id: str,
        action_id: str,
        body: InvestigationRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> InvestigationResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        if (
            state.content_version != "case001_1120"
            or state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise HTTPException(409, "Investigation unavailable")

        action = ACTION_CANDIDATES.get(action_id)

        approved_actions = getattr(
            request.app.state,
            "approved_investigation_actions",
            frozenset(),
        )

        if (
            action is None
            or not isinstance(approved_actions, frozenset)
            or action_id not in approved_actions
        ):
            raise HTTPException(404, "Action not found")

        if (
            state.current_chapter != action.chapter
            or action.chapter not in state.unlocked_chapters
        ):
            raise HTTPException(403, "Chapter unavailable")

        if action.evidence_id in {"E27", "E29"}:
            if not can_access_e26_section_for_state(
                "A",
                state,
                section_a_approved=getattr(
                    request.app.state,
                    "e26_section_a_approved",
                    False,
                ),
            ):
                raise HTTPException(
                    403, "Audit evidence access denied"
                )

            version = getattr(
                request.app.state,
                "investigation_release_version",
                None,
            )

            if not isinstance(version, str) or not version:
                raise HTTPException(
                    503, "Content release unavailable"
                )

        if not action.required_flags.issubset(state.flags):
            raise HTTPException(403, "Investigation requirements not satisfied")

        acquired = {
            eid
            for eid, item in state.evidence.items()
            if item.stage in {"found", "resolved"}
        }

        if not action.required_evidence.issubset(acquired):
            raise HTTPException(403, "Requirements not satisfied")

        if action.any_evidence and not action.any_evidence.intersection(acquired):
            raise HTTPException(403, "Requirements not satisfied")

        resources = getattr(
            request.app.state,
            "dialogue_resources",
            None,
        )

        rules = getattr(resources, "evidence_rules", None)

        routes = getattr(
            request.app.state,
            "approved_acquisition_routes",
            None,
        )

        if (
            not isinstance(rules, Mapping)
            or action.evidence_id not in rules
            or not isinstance(routes, Mapping)
        ):
            raise HTTPException(503, "Evidence engine unavailable")

        policy = routes.get(action.evidence_id)

        if (
            not isinstance(policy, AcquisitionPolicy)
            or policy.evidence_id != action.evidence_id
        ):
            raise HTTPException(503, "Acquisition route unavailable")

        # Only routes matching the verified scene action are allowed.
        selected_routes = [
            route
            for route in policy.routes
            if route.route_id in action.route_ids
            and route.action_flag == action.action_flag
            and route.chapter == action.chapter
            and route.policy.required_character == action.required_character
        ]

        if not selected_routes:
            raise HTTPException(503, "Acquisition route unavailable")

        selected_policy = AcquisitionPolicy(
            evidence_id=action.evidence_id,
            routes=selected_routes,
        )

        selection = repository.load_selection(session_id)

        if (
            selection is None
            or selection[1] != state.revision
            or selection[0] not in state.unlocked_characters
        ):
            raise HTTPException(409, "Invalid NPC selection")

        active_npc = selection[0]

        if (
            action.required_character is not None
            and action.required_character != active_npc
        ):
            raise HTTPException(403, "Required NPC not selected")

        # Stage the verified action; do not commit it independently.
        staged = GameState.model_validate(
            {
                **state.model_dump(),
                "flags": sorted(set(state.flags) | {action.action_flag}),
            }
        )

        if action.evidence_id == "E26":
            approved = getattr(
                request.app.state,
                "e26_section_a_approved",
                False,
            )

            version = getattr(
                request.app.state,
                "investigation_release_version",
                None,
            )

            if not isinstance(version, str) or not version:
                raise HTTPException(503, "Content release unavailable")

            if not can_acquire_e26_a(
                staged,
                section_a_approved=approved,
            ):
                raise HTTPException(403, "Audit access denied")

        if not allows_acquisition(
            selected_policy,
            staged,
            active_character_id=active_npc,
        ):
            raise HTTPException(403, "Acquisition denied")

        django = getattr(
            request.app.state,
            "django_content_client",
            None,
        )

        if not isinstance(django, DjangoContentClient):
            raise HTTPException(503, "Content service unavailable")

        try:
            release_version = getattr(
                request.app.state,
                "investigation_release_version",
                None,
            )

            scene = django.get_player_scene(
                state.case_id,
                action.scene_id,
                **(
                    {"investigation_release": release_version}
                    if release_version is not None
                    else {}
                ),
            )

            requirements = django.get_evidence_requirements(
                state.case_id,
                action.evidence_id,
            )

            if (
                scene.scene_id != action.scene_id
                or scene.chapter != action.chapter
                or requirements.evidence_id != action.evidence_id
            ):
                raise ContentServiceError("Content mismatch")

        except ContentServiceNotFoundError:
            raise HTTPException(404, "Action not found") from None

        except (ContentServiceError, ValueError):
            raise HTTPException(503, "Content approval unavailable") from None

        if action.evidence_id in {"E27", "E29"}:
            if set(requirements.prerequisites) != action.required_evidence:
                raise HTTPException(
                    503, "Follow-up evidence contract mismatch"
                )

        if not set(requirements.prerequisites).issubset(acquired):
            raise HTTPException(403, "Requirements not satisfied")

        try:
            progress = get_collection_progress(state, rules)

            if progress.score != state.score:
                raise ValueError("Score mismatch")

            if repository.load_state(session_id) != state:
                raise ValueError("Game state changed")

            if action.evidence_id in acquired:
                return InvestigationResponse(
                    evidenceId=action.evidence_id,
                    created=False,
                    score=state.score,
                    total=progress.total,
                    revision=state.revision,
                )

            result = collect_evidence(
                state=staged,
                evidence_id=action.evidence_id,
                evidence_rules=rules,
                acquisition_policy_ids={},
                evaluator=PolicyEvaluator({}),
                active_character_id=active_npc,
                approved_routes={
                    action.evidence_id: selected_policy,
                },
            )

            updated = stage_events(result.state)

            committed = repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        except ContentServiceError:
            raise HTTPException(503, "Story approval unavailable") from None

        except PermissionError:
            raise HTTPException(403, "Acquisition denied") from None

        except (ValueError, TypeError):
            raise HTTPException(409, "Game state changed") from None

        return InvestigationResponse(
            evidenceId=action.evidence_id,
            created=result.created,
            score=committed.score,
            total=result.progress.total,
            revision=committed.revision,
        )

    @router.post(
        "/api/games/{session_id}/scene-completions/sc-0203",
        response_model=SceneCompletionResponse,
    )
    def complete_sc0203(
        session_id: str,
        body: InvestigationRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> SceneCompletionResponse:
        state = load_owned_request(
            session_id,
            request,
            case001_owner,
        )

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        if (
            state.content_version != "case001_1120"
            or state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise HTTPException(409, "Scene unavailable")

        if (
            state.current_chapter != "CH02"
            or "CH02" not in state.unlocked_chapters
            or "C08" not in state.unlocked_characters
        ):
            raise HTTPException(403, "Scene unavailable")

        acquired = {
            eid
            for eid, item in state.evidence.items()
            if item.stage in {"found", "resolved"}
        }

        if not {"E13", "E14"}.issubset(acquired):
            raise HTTPException(403, "Missing evidence")

        selection = repository.load_selection(session_id)

        if selection != ("C08", state.revision):
            raise HTTPException(403, "Required NPC not selected")

        actions = getattr(
            request.app.state,
            "approved_investigation_actions",
            frozenset(),
        )

        if not isinstance(actions, frozenset) or "inspect-e14-a" not in actions:
            raise HTTPException(404, "Scene not published")

        django = getattr(
            request.app.state,
            "django_content_client",
            None,
        )

        version = getattr(
            request.app.state,
            "investigation_release_version",
            None,
        )

        if not isinstance(django, DjangoContentClient) or not isinstance(version, str):
            raise HTTPException(503, "Content service unavailable")

        try:
            scene = django.get_player_scene(
                state.case_id,
                "SC-0203",
                investigation_release=version,
            )

            if scene.scene_id != "SC-0203" or scene.chapter != "CH02":
                raise ContentServiceError("Scene mismatch")

            # Return only the approved NPC's original dialogue.
            marker = "**\uc11c\ubbf8\ub780:**"

            dialogue = [
                line.strip().removeprefix(marker).strip()
                for line in scene.scene_text.splitlines()
                if line.strip().startswith(marker)
            ]

            if len(dialogue) != 3 or not all(dialogue):
                raise ContentServiceError("Invalid scene dialogue")

        except ContentServiceNotFoundError:
            raise HTTPException(404, "Scene not published") from None

        except (ContentServiceError, ValueError):
            raise HTTPException(503, "Scene verification failed") from None

        flag = "ACT_SC0203_COMPLETED"

        if flag in state.flags:
            if (
                "E14" not in state.presented.get("C08", [])
                or state.npc_stages.get("C08", 1) < 2
            ):
                raise HTTPException(409, "Invalid scene state")

            return SceneCompletionResponse(
                sceneId="SC-0203",
                created=False,
                characterId="C08",
                presentedEvidenceId="E14",
                dialogue=dialogue,
                revision=state.revision,
            )

        # The endpoint itself represents presenting E14 to C08.
        presented = {
            **state.presented,
            "C08": sorted(set(state.presented.get("C08", [])) | {"E14"}),
        }

        updated = GameState.model_validate(
            {
                **state.model_dump(),
                "presented": presented,
                "npc_stages": {
                    **state.npc_stages,
                    "C08": max(2, state.npc_stages.get("C08", 1)),
                },
                "flags": sorted(set(state.flags) | {flag}),
                "revision": state.revision + 1,
            }
        )

        try:
            updated = stage_events(updated)

            committed = repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        except ContentServiceError:
            raise HTTPException(503, "Story approval unavailable") from None

        except (ValueError, TypeError):
            raise HTTPException(409, "Game state changed") from None

        return SceneCompletionResponse(
            sceneId="SC-0203",
            created=True,
            characterId="C08",
            presentedEvidenceId="E14",
            dialogue=dialogue,
            revision=committed.revision,
        )

    @router.post(
        "/api/games/{session_id}/legacy-evidence/{evidence_id}/inspect",
        response_model=InvestigationResponse,
    )
    def inspect_legacy_evidence(
        session_id: str,
        evidence_id: str,
        body: LegacyInspectionRequest,
        request: Request,
        case001_owner: str | None = Cookie(default=None),
    ) -> InvestigationResponse:
        state = load_owned_request(session_id, request, case001_owner)

        if state.revision != body.expectedRevision:
            raise HTTPException(409, "Game state changed")

        if (
            state.content_version != "case001_1120"
            or state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise HTTPException(409, "Investigation unavailable")

        if "CH01" not in state.unlocked_chapters:
            raise HTTPException(403, "Chapter unavailable")

        if evidence_id not in {
            "E01",
            "E02",
            "E03",
            "E04",
            "E05",
            "E06",
            "E08",
            "E09",
            "E10",
        }:
            raise HTTPException(404, "Evidence not published")

        resources = getattr(request.app.state, "dialogue_resources", None)

        rules = getattr(resources, "evidence_rules", None)

        routes = getattr(request.app.state, "approved_acquisition_routes", {})

        if not isinstance(rules, Mapping):
            raise HTTPException(503, "Evidence engine unavailable")

        if not isinstance(routes, Mapping):
            raise HTTPException(503, "Acquisition engine unavailable")

        policy = routes.get(evidence_id)

        if not isinstance(policy, AcquisitionPolicy):
            raise HTTPException(404, "Evidence not published")

        if (
            policy.evidence_id != evidence_id
            or evidence_id not in rules
            or len(policy.routes) != 1
        ):
            raise HTTPException(503, "Invalid acquisition contract")

        route = policy.routes[0]

        if route.route_id != f"{evidence_id}-LEGACY" or route.chapter != "CH01":
            raise HTTPException(503, "Invalid acquisition route")

        selection = repository.load_selection(session_id)

        if (
            selection is None
            or selection[1] != state.revision
            or selection[0] not in state.unlocked_characters
        ):
            raise HTTPException(409, "Invalid NPC selection")

        active_npc = selection[0]

        if active_npc != route.policy.required_character:
            raise HTTPException(403, "Required NPC not selected")

        acquired = {
            eid
            for eid, item in state.evidence.items()
            if item.stage in {"found", "resolved"}
        }

        if not set(route.policy.required_evidence).issubset(acquired):
            raise HTTPException(403, "Missing evidence")

        presented = {npc: list(ids) for npc, ids in state.presented.items()}

        # Support both legacy and multiple evidence presentations.
        if (
            body.presentedEvidenceId is not None
            and body.presentedEvidenceIds is not None
        ):
            raise HTTPException(422, "Ambiguous presentation request")

        submitted = (
            [body.presentedEvidenceId]
            if body.presentedEvidenceId is not None
            else body.presentedEvidenceIds or []
        )

        if len(submitted) > 10 or len(set(submitted)) != len(submitted):
            raise HTTPException(422, "Invalid presentation list")

        required_presentations = set(route.policy.required_presentations)

        if not all(
            eid in acquired and f"{active_npc}:{eid}" in required_presentations
            for eid in submitted
        ):
            raise HTTPException(403, "Presentation denied")

        if submitted:
            presented[active_npc] = sorted(
                set(presented.get(active_npc, [])) | set(submitted)
            )

        staged = GameState.model_validate(
            {
                **state.model_dump(),
                "presented": presented,
                "flags": sorted(set(state.flags) | {route.action_flag}),
            }
        )

        if not allows_acquisition(
            policy,
            staged,
            active_character_id=active_npc,
        ):
            raise HTTPException(403, "Acquisition denied")

        django = getattr(request.app.state, "django_content_client", None)

        if not isinstance(django, DjangoContentClient):
            raise HTTPException(503, "Content service unavailable")

        try:
            requirements = django.get_evidence_requirements(state.case_id, evidence_id)

            if requirements.evidence_id != evidence_id or set(
                requirements.prerequisites
            ) != set(route.policy.required_evidence):
                raise ContentServiceError("Evidence contract mismatch")

            progress = get_collection_progress(state, rules)

            if progress.score != state.score:
                raise ValueError("Score mismatch")

            if repository.load_state(session_id) != state:
                raise ValueError("Game state changed")

            if evidence_id in acquired:
                return InvestigationResponse(
                    evidenceId=evidence_id,
                    created=False,
                    score=state.score,
                    total=progress.total,
                    revision=state.revision,
                )

            result = collect_evidence(
                state=staged,
                evidence_id=evidence_id,
                evidence_rules=rules,
                acquisition_policy_ids={},
                evaluator=PolicyEvaluator({}),
                active_character_id=active_npc,
                approved_routes={evidence_id: policy},
            )

            updated = stage_events(result.state)

            committed = repository.commit_state(
                expected_state=state,
                updated_state=updated,
            )

        except ContentServiceNotFoundError:
            raise HTTPException(404, "Evidence not published") from None

        except ContentServiceError:
            raise HTTPException(503, "Content approval unavailable") from None

        except PermissionError:
            raise HTTPException(403, "Acquisition denied") from None

        except (TypeError, ValueError):
            raise HTTPException(409, "Game state changed") from None

        return InvestigationResponse(
            evidenceId=evidence_id,
            created=result.created,
            score=committed.score,
            total=result.progress.total,
            revision=committed.revision,
        )

    return router
