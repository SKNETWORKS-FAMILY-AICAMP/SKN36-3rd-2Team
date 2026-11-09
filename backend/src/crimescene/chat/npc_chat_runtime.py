"""Issue #23 - NPC RAG, Ollama, 출력 검증 및 세션 저장 통합."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from crimescene.chat.llm_client import generate_npc_json
from crimescene.chat.npc_history_context import (
    build_contextual_npc_reply_plan,
)
from crimescene.chat.npc_natural_reply import render_npc_speech
from crimescene.chat.npc_rag_service import (
    NPCRAGResources,
    prepare_npc_chat_rag,
)
from crimescene.chat.npc_reaction import (
    build_npc_reaction_prompt,
    detect_npc_reaction,
)
from crimescene.chat.npc_session import (
    NPCExchange,
    NPCSessionStore,
)
from crimescene.chat.npc_social_dialogue import (
    build_safe_social_reply,
    match_safe_social_intent,
)
from crimescene.retriever.npc_output_guard import (
    NPCGroundedReply,
    run_grounded_npc_response,
)
from crimescene.retriever.npc_response_gate import (
    FALLBACK_REPLY,
    NPCReplyPlan,
)
from crimescene.scenario.schemas.game_state import GameState


@dataclass(frozen=True, slots=True)
class NPCChatTurn:
    """검증된 NPC 대화 및 화면 표시 결과."""

    character_id: str
    reply: NPCGroundedReply
    exchange: NPCExchange
    display_text: str = ""


def run_npc_chat(
    query: str,
    *,
    state: GameState,
    session_store: NPCSessionStore,
    resources: NPCRAGResources,
    generate: Callable[[list[dict[str, str]]], str] = generate_npc_json,
    matched_topics: Iterable[str] = (),
    evidence_just_presented: bool = False,
) -> NPCChatTurn:
    """NPC 질문 처리부터 검증된 응답 저장까지 실행한다.

    보안 순서:
        1. 현재 NPC 기반 RAG 검색
        2. 접근 권한 검증 결과 확인
        3. Ollama 응답 생성
        4. 승인된 원문 인용 검증
        5. NPC 전환 및 GameState 변경 재확인
        6. 검증된 결과만 세션에 저장
    """

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(session_store, NPCSessionStore):
        raise TypeError("NPCSessionStore가 필요합니다.")

    if not callable(generate):
        raise TypeError("LLM 생성 함수가 필요합니다.")

    if not isinstance(evidence_just_presented, bool):
        raise TypeError("증거 제시 상태가 올바르지 않습니다.")

    initial_revision = state.revision

    # ==================================================
    # 1. 안전한 일상 대화 처리
    # ==================================================

    # 새로운 증거를 제시한 턴은 반드시 RAG 경로로 처리합니다.
    social_intent = None if evidence_just_presented else match_safe_social_intent(query)

    if social_intent is not None:
        character_id = session_store.get_active_npc(state)

        if character_id is None:
            raise PermissionError("현재 선택된 NPC가 없습니다.")

        history = session_store.get_history(
            state,
            character_id,
        )

        reaction = detect_npc_reaction(
            query,
            character_id=character_id,
            state=state,
            history=history,
        )

        social_text = build_safe_social_reply(
            character_id,
            query,
            repeated=reaction.mode == "repeated",
        )

        reply = NPCGroundedReply(
            text=social_text,
            source_ids=(),
            grounded=False,
        )

        if state.revision != initial_revision:
            raise RuntimeError("대화 처리 중 GameState가 변경됐습니다.")

        if session_store.get_active_npc(state) != character_id:
            raise RuntimeError("대화 처리 중 NPC가 변경됐습니다.")

        exchange = session_store.append_verified_exchange(
            state,
            character_id,
            user_message=query,
            reply=reply,
        )

        return NPCChatTurn(
            character_id=character_id,
            reply=reply,
            exchange=exchange,
            display_text=social_text,
        )

    # ==================================================
    # 2. 기존 Hybrid RAG 검색 및 권한 검증
    # ==================================================

    rag_result = prepare_npc_chat_rag(
        query,
        state=state,
        session_store=session_store,
        resources=resources,
        matched_topics=matched_topics,
    )

    character_id = rag_result.character_id
    plan = rag_result.reply_plan
    logging.getLogger(__name__).warning(
        "NPC_RAG_DIAG npc=%s topics=%s can_call_llm=%s source_count=%d target_found=%s",
        character_id,
        tuple(matched_topics),
        plan.can_call_llm,
        len(plan.source_ids),
        "K-C01-03" in plan.source_ids,
    )
    if not isinstance(plan, NPCReplyPlan):
        raise TypeError("NPCReplyPlan이 필요합니다.")

    if plan.can_call_llm:
        context = plan.authorized_context

        if context is None:
            raise RuntimeError("검증된 RAG 컨텍스트가 없습니다.")

        # 기존 검증된 대화 이력 연결
        contextual_plan = build_contextual_npc_reply_plan(
            plan,
            rag_result.history,
            current_revision=state.revision,
        )

        # 새 증거 제시 여부를 NPC 반응 프롬프트에 반영
        reaction_prompt = build_npc_reaction_prompt(
            query,
            character_id=character_id,
            state=state,
            history=rag_result.history,
            evidence_just_presented=evidence_just_presented,
        )

        if len(contextual_plan.messages) != 2:
            raise ValueError("NPC 메시지 형식이 올바르지 않습니다.")

        system_message, user_message = contextual_plan.messages

        if system_message.get("role") != "system" or user_message.get("role") != "user":
            raise ValueError("NPC 메시지 역할이 올바르지 않습니다.")

        contextual_plan = replace(
            contextual_plan,
            messages=(
                {
                    **system_message,
                    "content": (system_message["content"] + "\n\n" + reaction_prompt),
                },
                user_message,
            ),
        )

        # 기존 RAG 원문 및 출처 검증 유지
        reply = run_grounded_npc_response(
            contextual_plan,
            context,
            generate=generate,
        )

    else:
        # 승인된 근거가 없으면 LLM을 호출하지 않습니다.
        if (
            plan.fallback_reply != FALLBACK_REPLY
            or plan.messages
            or plan.source_ids
            or plan.authorized_context is not None
        ):
            raise ValueError("차단된 NPC 응답 계획이 올바르지 않습니다.")

        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

    # ==================================================
    # 3. GameState 및 NPC 선택 상태 재검증
    # ==================================================

    if state.revision != initial_revision:
        raise RuntimeError("대화 처리 중 GameState가 변경됐습니다.")

    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("대화 처리 중 NPC가 변경됐습니다.")

    # ==================================================
    # 4. Issue #25 - 자연스러운 NPC 말풍선 생성
    # ==================================================

    display_text = reply.text

    if reply.grounded:
        # 새 증거 제시가 반복 질문보다 우선합니다.
        reaction = detect_npc_reaction(
            query,
            character_id=character_id,
            state=state,
            history=rag_result.history,
            evidence_just_presented=evidence_just_presented,
        )

        display_text = render_npc_speech(
            reply,
            context=context,
            reaction=reaction,
        )

    # ==================================================
    # 5. 검증된 NPC 응답 저장
    # ==================================================

    # 화면용 display_text는 저장하지 않습니다.
    # 기존 원문과 출처를 유지해 RAG 인용 검증을 보호합니다.
    exchange = session_store.append_verified_exchange(
        state,
        character_id,
        user_message=query,
        reply=reply,
    )

    return NPCChatTurn(
        character_id=character_id,
        reply=reply,
        exchange=exchange,
        display_text=display_text,
    )
