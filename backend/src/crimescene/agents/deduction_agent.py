
"""Issue #132 - 보유 증거 기반 읽기 전용 Deduction Agent."""

import re
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.agents.deduction_documents import (
    DeductionDocument,
    select_visible_deduction_documents,
)
from crimescene.agents.deduction_relations import (
    DeductionRelation,
    select_visible_deduction_relations,
)
from crimescene.scenario.game_progress import CASE_ID
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GamePhase, GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

EVIDENCE_ID_PATTERN = re.compile(r"E(?:0[1-9]|10)")
MENTION_PATTERN = re.compile(r"(?<![A-Za-z0-9_])E\d{2}(?![A-Za-z0-9_])")
VALID_STAGES = frozenset({"found", "resolved"})


class DeductionStatus(StrEnum):
    """현재 공개 정보만으로 내릴 수 있는 검토 결과."""

    RELATED_EVIDENCE = "RELATED_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DeductionResult(AgentResult):
    """공개된 근거만 포함하는 추리 검토 결과."""

    status: DeductionStatus
    verdict: str = "UNVERIFIED"
    contradiction: str = "NOT_DETERMINED"
    relations: tuple[DeductionRelation, ...] = ()
    documents: tuple[DeductionDocument, ...] = ()


class DeductionAgent:
    """서버가 확인한 보유 증거만 사용하여 추리 근거를 검토합니다."""



    def __init__(
        self,
        *,
        load_state: Callable[[str], GameState],
        evidence_rules: Mapping[str, EvidenceRule],
        trusted_edges: Sequence[RelationshipSourceEdge] = (),
        documents: Sequence[PlayerDocument] = (),
        evaluator: PolicyEvaluator | None = None,
    ) -> None:
        if not callable(load_state):
            raise TypeError("GameState 조회 함수가 필요합니다.")

        if not isinstance(evidence_rules, Mapping):
            raise TypeError("증거 규칙은 Mapping이어야 합니다.")

        validated: dict[str, EvidenceRule] = {}

        for evidence_id, rule in evidence_rules.items():
            if (
                not isinstance(evidence_id, str)
                or EVIDENCE_ID_PATTERN.fullmatch(evidence_id) is None
                or not isinstance(rule, EvidenceRule)
            ):
                raise TypeError("유효하지 않은 증거 규칙입니다.")

            validated[evidence_id] = rule.model_copy(deep=True)

        edges = tuple(trusted_edges)

        if any(
            not isinstance(edge, RelationshipSourceEdge)
            for edge in edges
        ):
            raise TypeError("검증되지 않은 관계 데이터입니다.")

        server_documents = tuple(documents)

        if any(
            not isinstance(document, PlayerDocument)
            for document in server_documents
        ):
            raise TypeError("검증되지 않은 문서 데이터입니다.")

        # 문서가 존재하지만 공개 정책이 없으면 접근을 차단합니다.
        if server_documents and not isinstance(evaluator, PolicyEvaluator):
            raise TypeError("문서 접근 정책 엔진이 필요합니다.")

        if evaluator is not None and not isinstance(
            evaluator, PolicyEvaluator
        ):
            raise TypeError("올바른 PolicyEvaluator가 필요합니다.")

        self._load_state = load_state
        self._rules = MappingProxyType(validated)
        self._edges = tuple(edge.model_copy(deep=True) for edge in edges)
        self._documents = tuple(
            document.model_copy(deep=True)
            for document in server_documents
        )
        self._evaluator = evaluator


    @property
    def agent_type(self) -> AgentType:
        return AgentType.DEDUCTION

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> DeductionResult:
        """미획득 증거를 배제한 상태에서 증거 관련성을 검토합니다."""

        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest가 필요합니다.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext가 필요합니다.")

        if request.agent_type != AgentType.DEDUCTION:
            raise ValueError("Deduction Agent 요청이 아닙니다.")

        # 호출자가 전달한 스냅샷을 신뢰하지 않고 서버 상태를 재조회합니다.
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
            raise PermissionError("조사 단계에서만 추론할 수 있습니다.")

        if any(
            item.stage not in VALID_STAGES
            for item in state.evidence.values()
        ):
            raise PermissionError("유효하지 않은 증거 상태입니다.")

        # 실제로 획득했고, 서버 증거 규칙에도 존재하는 ID만 허용합니다.
        collected = set(state.evidence) & set(self._rules)

        # 사용자가 임의로 입력한 미획득 증거 ID를 차단합니다.
        mentioned_ids = set(MENTION_PATTERN.findall(request.message))

        if not mentioned_ids.issubset(collected):
            raise PermissionError("사용할 수 없는 증거가 포함됐습니다.")

        # MVP: 보유 증거의 ID 또는 정확한 이름이 언급됐는지만 확인합니다.
        related_ids = tuple(
            sorted(
                evidence_id
                for evidence_id in collected
                if (
                    evidence_id in mentioned_ids
                    or self._rules[evidence_id].name in request.message
                )
            )
        )

        if not related_ids:
            return DeductionResult(
                agent_type=AgentType.DEDUCTION,
                text=(
                    "현재 주장에 직접 연결된 보유 증거를 확인하지 못했습니다. "
                    "수집한 증거의 이름이나 번호를 함께 제시해 주세요."
                ),
                source_ids=(),
                status=DeductionStatus.INSUFFICIENT_EVIDENCE,
            )



        # 기존 공개 관계 정책을 통과한 관계만 조회합니다.
        relations = select_visible_deduction_relations(
            state=state,
            trusted_edges=self._edges,
            related_evidence_ids=related_ids,
        )

        # 문서 공개 정책이 없는 경우 문서 조회를 허용하지 않습니다.
        documents = (
            select_visible_deduction_documents(
                state=state,
                documents=self._documents,
                evaluator=self._evaluator,
                related_evidence_ids=related_ids,
            )
            if self._evaluator is not None and self._documents
            else ()
        )

        names = ", ".join(
            self._rules[evidence_id].name
            for evidence_id in related_ids
        )

        relation_text = ""
        if relations:
            summaries = [
                (
                    f"{item.source_id} - {item.relation} - "
                    f"{item.target_id} ({item.truth_status})"
                )
                for item in relations
            ]
            relation_text = " 공개 관계: " + "; ".join(summaries) + "."

        document_text = ""
        if documents:
            titles = ", ".join(document.title for document in documents)
            document_text = f" 열람 가능한 관련 문서: {titles}."

        return DeductionResult(
            agent_type=AgentType.DEDUCTION,
            text=(
                f"함께 검토할 수 있는 보유 증거: {names}."
                f"{relation_text}"
                f"{document_text} "
                "현재 공개된 정보만으로 추리 주장의 진위나 "
                "모순 여부를 확정할 수는 없습니다."
            ),
            source_ids=related_ids,
            status=DeductionStatus.RELATED_EVIDENCE,
            relations=relations,
            documents=documents,
        )
