"""Versioned evidence acquisition route policies."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
    GameState,
)

EXTENDED_EVIDENCE_IDS = frozenset(
    f"E{i:02d}" for i in range(11, 31)
)


class AcquisitionRoute(BaseModel):
    """One server-verified acquisition route."""

    model_config = ConfigDict(extra="forbid", strict=True)

    route_id: str = Field(min_length=1)
    chapter: ChapterCode
    action_flag: str = Field(
        pattern=r"^ACT_[A-Z0-9_]+$",
        max_length=128,
    )
    policy: AccessPolicy


class AcquisitionPolicy(BaseModel):
    """Alternative acquisition routes for one evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str = Field(
        pattern=r"^E(0[1-9]|[12][0-9]|30)$",
    )
    routes: list[AcquisitionRoute] = Field(min_length=1)


def allows_acquisition(
    policy: AcquisitionPolicy,
    state: GameState,
    *,
    active_character_id: str | None = None,
    matched_topics: Iterable[str] = (),
) -> bool:
    """Allow acquisition only through a verified route."""

    if not isinstance(policy, AcquisitionPolicy):
        raise TypeError("AcquisitionPolicy required")

    if not isinstance(state, GameState):
        raise TypeError("GameState required")

    if state.case_id != "CASE-001":
        return False

    if state.phase != GamePhase.INVESTIGATION:
        return False

    if state.outcome not in (None, "ONGOING"):
        return False

    topics = tuple(matched_topics)

    for route in policy.routes:

        if route.chapter not in state.unlocked_chapters:
            continue

        # The flag must originate from a verified server action.
        if route.action_flag not in state.flags:
            continue

        evaluator = PolicyEvaluator({
            "POL-ACQUISITION": route.policy,
        })

        if evaluator.is_allowed(
            "POL-ACQUISITION",
            state,
            active_character_id=active_character_id,
            matched_topics=topics,
        ):
            return True

    return False
