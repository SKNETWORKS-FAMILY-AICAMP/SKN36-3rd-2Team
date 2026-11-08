"""CASE-001 증거 제시, NPC 트리거, Hybrid RAG의 서버 측 연결 계층."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from crimescene.chat.npc_chat_runtime import NPCChatTurn, run_npc_chat
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import NPCSessionStore
from crimescene.scenario.npc_access import (
    NPCKnowledgeCardV71,
    select_authorized_npc_cards,
)
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.evidence_presentation import process_npc_dialogue_event
from crimescene.trigger.npc_trigger import NPCTriggerRule


@dataclass(frozen=True, slots=True)
class Case001DialogueResult:
    """검증된 NPC 답변과 호출자가 영구 저장할 새 게임 상태."""

    turn: NPCChatTurn
    state: GameState
    presentation_created: bool
    trigger_ids: tuple[str, ...]
    disclosed_card_ids: tuple[str, ...]


def build_case001_recipients(
    *,
    policies: Mapping[str, AccessPolicy],
    npc_cards: Iterable[Mapping[str, object]],
    evidence_rules: Mapping[str, EvidenceRule],
) -> dict[str, frozenset[str]]:
    """실제 지식 카드와 접근 정책에 명시된 증거 제시 대상만 허용한다.

    증거 규칙의 presentation 필드는 의미가 확정되지 않아
    권한으로 사용하지 않는다.
    """

    if not isinstance(policies, Mapping):
        raise TypeError("접근 정책은 매핑이어야 합니다.")

    if not isinstance(evidence_rules, Mapping):
        raise TypeError("증거 규칙은 매핑이어야 합니다.")

    recipients: dict[str, set[str]] = defaultdict(set)
    seen_card_ids: set[str] = set()

    for raw_card in npc_cards:
        card = NPCKnowledgeCardV71.model_validate(raw_card)

        if card.id in seen_card_ids:
            raise ValueError("중복된 NPC 지식 카드 ID입니다.")

        seen_card_ids.add(card.id)

        if card.case_id != "CASE-001":
            continue

        policy = policies.get(card.policy_id)

        if policy is None:
            continue

        if not isinstance(policy, AccessPolicy):
            raise TypeError("접근 정책 타입이 올바르지 않습니다.")

        if policy.required_character not in (None, card.character_id):
            continue

        requirements = (
            *policy.required_presentations,
            *card.required_presentations,
        )

        for requirement in requirements:
            parts = requirement.split(":")

            if len(parts) != 2:
                continue

            npc_id, evidence_id = parts

            if npc_id != card.character_id:
                continue

            if evidence_id not in evidence_rules:
                continue

            recipients[evidence_id].add(npc_id)

    return {
        evidence_id: frozenset(npc_ids) for evidence_id, npc_ids in recipients.items()
    }


def run_case001_npc_dialogue(
    question: str,
    *,
    state: GameState,
    session_store: NPCSessionStore,
    resources: NPCRAGResources,
    policies: Mapping[str, AccessPolicy],
    trigger_rules: Iterable[NPCTriggerRule],
    presented_evidence_id: str | None = None,
) -> Case001DialogueResult:
    """증거 제시 → 승인된 트리거 → 기존 보안 RAG → 실제 인용 카드 기록.

    상태를 저장하지 않는다.
    호출자가 변경된 GameState를 영구 저장해야 한다.
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(session_store, NPCSessionStore):
        raise TypeError("NPCSessionStore가 필요합니다.")

    if not isinstance(resources, NPCRAGResources):
        raise TypeError("NPCRAGResources가 필요합니다.")

    active_npc = session_store.get_active_npc(state)

    if active_npc is None or active_npc not in state.unlocked_characters:
        raise PermissionError("현재 대화 가능한 NPC가 없습니다.")

    # 실제 접근 정책과 NPC 지식 카드에서
    # 증거별 제시 가능한 NPC 목록을 계산한다.
    recipients = build_case001_recipients(
        policies=policies,
        npc_cards=resources.npc_cards,
        evidence_rules=resources.evidence_rules,
    )

    # 증거 제시와 질문 트리거를 적용한다.
    event = process_npc_dialogue_event(
        question,
        state=state,
        active_character_id=active_npc,
        trigger_rules=trigger_rules,
        evaluator=resources.evaluator,
        evidence_rules=resources.evidence_rules,
        allowed_recipients=recipients,
        presented_evidence_id=presented_evidence_id,
    )

    # matched_topics는 플레이어 입력이 아니라
    # 서버 정책 검증을 통과한 결과만 사용한다.
    turn = run_npc_chat(
        question,
        state=event.state,
        session_store=session_store,
        resources=resources,
        matched_topics=event.matched_topics,
    )

    # NPC가 실제 인용한 지식 카드만 공개 완료 처리한다.
    disclosed: list[str] = []
    next_state = event.state

    if turn.reply.grounded:
        approved_cards = select_authorized_npc_cards(
            resources.npc_cards,
            event.state,
            resources.evaluator,
            active_character_id=active_npc,
            matched_topics=event.matched_topics,
        )

        authorized_ids = {card.card_id for card in approved_cards}

        already_disclosed = set(event.state.disclosed_cards)

        for source_id in turn.reply.source_ids:
            if source_id not in authorized_ids:
                continue

            if source_id in already_disclosed:
                continue

            disclosed.append(source_id)
            already_disclosed.add(source_id)

        if disclosed:
            next_state = GameState.model_validate(
                {
                    **event.state.model_dump(),
                    "disclosed_cards": [
                        *event.state.disclosed_cards,
                        *disclosed,
                    ],
                    "revision": event.state.revision + 1,
                }
            )

    return Case001DialogueResult(
        turn=turn,
        state=next_state,
        presentation_created=event.presentation_created,
        trigger_ids=event.trigger_ids,
        disclosed_card_ids=tuple(disclosed),
    )
