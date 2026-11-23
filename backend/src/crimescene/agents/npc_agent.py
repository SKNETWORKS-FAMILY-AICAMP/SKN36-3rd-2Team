"""Issue #131 - 기존 NPC 대화 엔진 Agent Adapter."""

from collections.abc import Mapping

from pydantic import Field, SkipValidation

from crimescene.agents.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    AgentType,
)
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import MAX_MESSAGE_LENGTH
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
)
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.trigger.atomic_dialogue import (
    SQLiteCase001Repository,
    run_case001_npc_dialogue_atomic,
)
from crimescene.trigger.case001_dialogue import (
    Case001DialogueResult,
    build_case001_recipients,
)
from crimescene.trigger.evidence_reaction import (
    resolve_evidence_reaction,
)
from crimescene.trigger.npc_trigger import NPCTriggerRule


class NPCEvidenceReactionError(ValueError):
    """증거 제시 질문 구성에 실패했습니다."""


class NPCDisplayError(ValueError):
    """NPC 화면 표시 응답이 올바르지 않습니다."""


class NPCAgentResult(AgentResult):
    """기존 대화 결과를 보존하는 NPC 전용 내부 결과."""

    dialogue: SkipValidation[Case001DialogueResult] = Field(
        exclude=True,
        repr=False,
    )


class NPCAgent:
    """기존 원자적 NPC 대화 엔진을 Agent 인터페이스로 연결합니다."""

    def __init__(
        self,
        *,
        repository: SQLiteCase001Repository,
        resources: NPCRAGResources,
        policies: Mapping[str, AccessPolicy],
        trigger_rules: tuple[NPCTriggerRule, ...] = (),
        flag_config: Case001UnlockRules | None = None,
    ) -> None:
        if not isinstance(repository, SQLiteCase001Repository):
            raise TypeError("SQLiteCase001Repository가 필요합니다.")

        if not isinstance(resources, NPCRAGResources):
            raise TypeError("NPCRAGResources가 필요합니다.")

        if not isinstance(policies, Mapping):
            raise TypeError("접근 정책은 Mapping이어야 합니다.")

        if not isinstance(trigger_rules, tuple):
            raise TypeError("트리거 규칙은 tuple이어야 합니다.")

        self._repository = repository
        self._resources = resources
        self._policies = dict(policies)
        self._trigger_rules = trigger_rules
        self._flag_config = flag_config

    @property
    def agent_type(self) -> AgentType:
        return AgentType.NPC

    def execute(
        self,
        request: AgentRequest,
        *,
        context: AgentContext,
    ) -> NPCAgentResult:
        """검증된 컨텍스트를 사용하여 기존 대화 엔진을 한 번 호출합니다."""

        if not isinstance(request, AgentRequest):
            raise TypeError("AgentRequest가 필요합니다.")

        if not isinstance(context, AgentContext):
            raise TypeError("AgentContext가 필요합니다.")

        if request.agent_type != AgentType.NPC:
            raise ValueError("NPC Agent 요청이 아닙니다.")

        active_npc = context.active_character_id

        if active_npc is None:
            raise PermissionError("현재 선택된 NPC가 없습니다.")

        question = request.message
        evidence_id = request.presented_evidence_id

        if evidence_id is not None:
            if evidence_id not in context.collected_evidence_ids:
                raise PermissionError("수집하지 않은 증거입니다.")

            # 기존 증거 반응 및 NPC별 제시 허용 정책 유지
            recipients = build_case001_recipients(
                policies=self._policies,
                npc_cards=self._resources.npc_cards,
                evidence_rules=self._resources.evidence_rules,
            )

            try:
                question, evidence_id = resolve_evidence_reaction(
                    question,
                    evidence_id,
                    active_npc=active_npc,
                    rules=self._resources.evidence_rules,
                    authorized_recipients=recipients,
                    max_length=MAX_MESSAGE_LENGTH,
                )
            except ValueError as exc:
                raise NPCEvidenceReactionError(
                    "증거 데이터가 올바르지 않습니다."
                ) from exc

        # 기존 RAG, 출력 검증, SQLite 원자적 저장 경로 재사용
        dialogue = run_case001_npc_dialogue_atomic(
            question,
            session_id=context.session_id,
            repository=self._repository,
            resources=self._resources,
            policies=self._policies,
            trigger_rules=self._trigger_rules,
            presented_evidence_id=evidence_id,
            flag_config=self._flag_config,
        )

        if not isinstance(dialogue, Case001DialogueResult):
            raise TypeError("NPC 대화 결과 형식이 올바르지 않습니다.")

        if (
            dialogue.state.session_id != context.session_id
            or dialogue.state.case_id != context.case_id
            or dialogue.turn.character_id != active_npc
        ):
            raise RuntimeError("NPC 대화 결과의 세션 또는 NPC가 일치하지 않습니다.")

        display_text = dialogue.turn.display_text

        if not isinstance(display_text, str) or not display_text.strip():
            raise NPCDisplayError("NPC 응답 형식이 올바르지 않습니다.")

        return NPCAgentResult(
            agent_type=AgentType.NPC,
            text=display_text,
            source_ids=dialogue.turn.reply.source_ids,
            dialogue=dialogue,
        )