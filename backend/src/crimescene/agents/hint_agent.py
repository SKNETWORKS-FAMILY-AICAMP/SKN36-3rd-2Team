
"""Issue #133 - GameState 기반 3단계 Hint Agent.

Python 3.13 / Pydantic 2
"""

import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import Field

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.scenario.evidence_collection import get_collection_progress
from crimescene.scenario.game_progress import CASE_ID, EXPECTED_EVIDENCE_IDS
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import (
    ChapterCode,
    GamePhase,
    GameState,
)

LEVEL_PATTERN = re.compile(r"(?<!\d)(\d+)\s*단계")


class HintStatus(StrEnum):
    READY = "READY"
    NO_EVIDENCE = "NO_EVIDENCE"


class HintResult(AgentResult):
    """플레이어에게 공개 가능한 힌트 실행 결과."""

    level: int = Field(ge=1, le=3)
    status: HintStatus
    chapter: ChapterCode
    collected_count: int = Field(ge=0)
    suggested_character_id: str | None = None


def parse_hint_level(message: str) -> int:
    """명시적 힌트 단계를 읽고, 미지정 시 1단계를 사용합니다."""

    if not isinstance(message, str) or not message.strip():
        raise ValueError("힌트 요청이 비어 있습니다.")

    matches = LEVEL_PATTERN.findall(message)

    if len(matches) > 1:
        raise ValueError("힌트 단계는 하나만 지정할 수 있습니다.")

    if not matches:
        return 1

    level = int(matches[0])

    if level not in (1, 2, 3):
        raise ValueError("힌트 단계는 1~3단계만 허용됩니다.")

    return level


class HintAgent:
    """현재 공개된 진행 상태만 활용하는 읽기 전용 Agent."""

    def __init__(
        self,
        *,
        load_state: Callable[[str], GameState],
        evidence_rules: Mapping[str, EvidenceRule],
    ) -> None:
        if not callable(load_state):
            raise TypeError("GameState 조회 함수가 필요합니다.")

        if not isinstance(evidence_rules, Mapping) or not evidence_rules:
            raise ValueError("유효한 증거 규칙이 필요합니다.")

        validated: dict[str, EvidenceRule] = {}

        for evidence_id, rule in evidence_rules.items():
            if evidence_id not in EXPECTED_EVIDENCE_IDS:
                raise ValueError("지원하지 않는 증거 ID입니다.")

            if not isinstance(rule, EvidenceRule):
                raise TypeError("유효하지 않은 증거 규칙입니다.")

            validated[evidence_id] = rule.model_copy(deep=True)

        self._load_state = load_state
        self._rules = MappingProxyType(validated)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.HINT

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> HintResult:
        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest가 필요합니다.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext가 필요합니다.")

        if request.agent_type != AgentType.HINT:
            raise ValueError("Hint Agent 요청이 아닙니다.")

        level = parse_hint_level(request.message)

        # 클라이언트가 제공한 상태가 아닌 서버 상태를 재조회합니다.
        state = self._load_state(context.session_id)

        if not isinstance(state, GameState):
            raise TypeError("올바른 GameState가 필요합니다.")

        if (
            state.case_id != CASE_ID
            or state.session_id != context.session_id
        ):
            raise PermissionError("게임 세션 또는 사건이 일치하지 않습니다.")

        expected_context = AgentContext.from_game_state(
            state,
            active_character_id=context.active_character_id,
        )

        if context != expected_context:
            raise RuntimeError("게임 상태 스냅샷이 변경됐습니다.")

        if (
            state.phase != GamePhase.INVESTIGATION
            or state.outcome not in (None, "ONGOING")
        ):
            raise PermissionError("조사 단계에서만 힌트를 제공할 수 있습니다.")

        # 기존 증거 수집 엔진으로 증거 상태 및 점수를 검증합니다.
        progress = get_collection_progress(state, self._rules)

        if state.score != progress.score:
            raise ValueError("증거 수집 점수가 일치하지 않습니다.")

        collected = tuple(sorted(state.evidence))
        unlocked = tuple(sorted(state.unlocked_characters))

        if level == 1:
            return HintResult(
                agent_type=AgentType.HINT,
                text=(
                    f"현재 {state.current_chapter} 챕터를 조사 중입니다. "
                    "지금까지 공개된 대화와 기록을 다시 확인하고, "
                    "아직 확인하지 않은 질문이 있는지 살펴보세요."
                ),
                source_ids=(),
                level=1,
                status=HintStatus.READY,
                chapter=state.current_chapter,
                collected_count=progress.collected_count,
            )

        if level == 2:
            if not collected:
                return HintResult(
                    agent_type=AgentType.HINT,
                    text=(
                        "아직 확보한 증거가 없습니다. "
                        "현재 공개된 NPC 대화와 조사 기록부터 확인해 보세요."
                    ),
                    source_ids=(),
                    level=2,
                    status=HintStatus.NO_EVIDENCE,
                    chapter=state.current_chapter,
                    collected_count=0,
                )

            # 두 증거 사이의 관계를 만들어내지 않고 비교만 권유합니다.
            selected = collected[:2]

            if len(selected) == 1:
                text = (
                    f"이미 확보한 {selected[0]}의 내용을 다시 확인해 보세요. "
                    "기록에 실제로 등장하는 인물과 시간 정보를 구분해 보세요."
                )
            else:
                text = (
                    f"이미 확보한 {selected[0]}과 {selected[1]}을 "
                    "나란히 검토해 보세요. 두 기록에 공통된 정보가 있는지, "
                    "차이가 있다면 무엇인지 확인해 보세요."
                )

            return HintResult(
                agent_type=AgentType.HINT,
                text=text,
                source_ids=selected,
                level=2,
                status=HintStatus.READY,
                chapter=state.current_chapter,
                collected_count=progress.collected_count,
            )

        # 3단계: 이미 해금된 NPC와 수집한 증거만 사용합니다.
        if not unlocked:
            return HintResult(
                agent_type=AgentType.HINT,
                text=(
                    "현재 열람 가능한 조사 기록을 다시 확인해 보세요. "
                    "공개되지 않은 인물이나 증거는 안내하지 않습니다."
                ),
                source_ids=(),
                level=3,
                status=(
                    HintStatus.READY
                    if collected
                    else HintStatus.NO_EVIDENCE
                ),
                chapter=state.current_chapter,
                collected_count=progress.collected_count,
            )

        # 보유 증거의 서버 규칙에 등록된 인물이 해금되어 있다면 우선 안내
        selected_evidence = collected[0] if collected else None
        character_id = unlocked[0]

        if selected_evidence is not None:
            holder = self._rules[selected_evidence].holder

            if holder in unlocked:
                character_id = holder

            text = (
                f"현재 해금된 {character_id}에게 "
                f"이미 확보한 {selected_evidence}에 관해 "
                "확인 질문을 해 보세요. "
                "인물의 답변과 공개된 기록을 직접 비교해 보세요."
            )
            sources = (selected_evidence,)
        else:
            text = (
                f"현재 해금된 {character_id}에게 "
                "지금까지 공개된 사건 경위를 다시 질문해 보세요. "
                "답변에서 확인 가능한 사실을 구분하는 것이 좋습니다."
            )
            sources = ()

        return HintResult(
            agent_type=AgentType.HINT,
            text=text,
            source_ids=sources,
            level=3,
            status=(
                HintStatus.READY
                if collected
                else HintStatus.NO_EVIDENCE
            ),
            chapter=state.current_chapter,
            collected_count=progress.collected_count,
            suggested_character_id=character_id,
        )
