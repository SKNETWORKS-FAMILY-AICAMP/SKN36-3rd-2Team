
"""Issue #23 - NPC RAG, Ollama, 출력 검증 및 세션 저장 통합."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from crimescene.chat.llm_client import generate_npc_json
from crimescene.chat.npc_memory_recall import (
    build_memory_recall_from_history,
    is_memory_recall_question,
)
from crimescene.chat.npc_conversation_memory import (
    build_revalidated_repeat_output,
)
from crimescene.chat.npc_dialogue_intent import build_npc_intent_prompt
from crimescene.chat.npc_dynamic_persona import build_dynamic_npc_prompt
from crimescene.chat.npc_emotional_state import (
    build_npc_emotion_prompt,
    derive_npc_emotional_state,
)
from crimescene.chat.npc_evidence_dialogue import (
    EvidenceDialogueContext,
    build_evidence_dialogue_prompt,
)
from crimescene.chat.npc_history_context import (
    build_contextual_npc_reply_plan,
)
from crimescene.chat.npc_natural_reply import render_npc_speech
from crimescene.chat.npc_rag_service import (
    NPCRAGResources,
    prepare_npc_chat_rag,
)
from crimescene.chat.npc_pressure_dialogue import (
    build_pressure_reply,
    is_generic_pressure_question,
    pressure_dialogue_enabled,
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
    generate: Callable[
        [list[dict[str, str]]],
        str,
    ] = generate_npc_json,
    matched_topics: Iterable[str] = (),
    evidence_just_presented: bool = False,
    evidence_dialogue: EvidenceDialogueContext | None = None,
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

    # ==================================================
    # 1. 입력 검증
    # ==================================================

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(session_store, NPCSessionStore):
        raise TypeError("NPCSessionStore가 필요합니다.")

    if not callable(generate):
        raise TypeError("LLM 생성 함수가 필요합니다.")

    if not isinstance(evidence_just_presented, bool):
        raise TypeError(
            "증거 제시 상태가 올바르지 않습니다."
        )

    if isinstance(matched_topics, (str, bytes)):
        raise TypeError(
            "질문 주제는 문자열 목록이어야 합니다."
        )

    topics = tuple(matched_topics)

    if evidence_dialogue is not None:
        if not isinstance(evidence_dialogue, EvidenceDialogueContext):
            raise TypeError("Invalid evidence dialogue context")

        evidence_dialogue.validate(
            state,
            session_store.get_active_npc(state),
        )

        if (
            evidence_dialogue.first_presentation
            != evidence_just_presented
        ):
            raise PermissionError("Presentation status mismatch")

    evidence_turn = (
        evidence_just_presented
        or evidence_dialogue is not None
    )

    initial_revision = state.revision

    # ==================================================
    # 2. 안전한 일상 대화 처리
    # ==================================================

    # 증거를 제시한 턴은 반드시 RAG 경로로 처리
    social_intent = (
        None
        if evidence_turn
        else match_safe_social_intent(query)
    )

    recall_requested = (
        state.case_id == "CASE-001"
        and state.content_version == "case001_1120"
        and not evidence_turn
        and is_memory_recall_question(query)
    )

    pressure_requested = (
        not evidence_turn
        and pressure_dialogue_enabled(state)
        and is_generic_pressure_question(query)
    )

    if (
        social_intent is not None
        or recall_requested
        or pressure_requested
    ):
        character_id = session_store.get_active_npc(state)

        if character_id is None:
            raise PermissionError(
                "현재 선택된 NPC가 없습니다."
            )

        history = session_store.get_history(
            state,
            character_id,
        )

        if pressure_requested:
            emotion = derive_npc_emotional_state(
                query,
                state=state,
                character_id=character_id,
                history=history,
                evidence_just_presented=False,
            )

            social_text = build_pressure_reply(
                query,
                state=state,
                character_id=character_id,
                emotion=emotion,
            )

        elif recall_requested:
            social_text = (
                build_memory_recall_from_history(
                    character_id,
                    query,
                    history,
                    current_revision=state.revision,
                )
                or FALLBACK_REPLY
            )

        else:
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
            raise RuntimeError(
                "대화 처리 중 GameState가 변경됐습니다."
            )

        if session_store.get_active_npc(state) != character_id:
            raise RuntimeError(
                "대화 처리 중 NPC가 변경됐습니다."
            )

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
    # 3. Hybrid RAG 검색 및 권한 검증
    # ==================================================

    rag_result = prepare_npc_chat_rag(
        query,
        state=state,
        session_store=session_store,
        resources=resources,
        matched_topics=topics,
        **(
            {"evidence_dialogue": evidence_dialogue}
            if evidence_dialogue is not None else {}
        ),
        **(
            {"use_memory_context": True}
            if (
                state.content_version == "case001_1120"
                and not evidence_turn
            )
            else {}
        ),
    )

    character_id = rag_result.character_id
    plan = rag_result.reply_plan

    if evidence_dialogue is not None:
        evidence_dialogue.validate(state, character_id)

    if not isinstance(plan, NPCReplyPlan):
        raise TypeError("NPCReplyPlan이 필요합니다.")

    # ==================================================
    # 4. Ollama 호출 및 근거 인용 검증
    # ==================================================

    emotion = None

    if (
        state.content_version == "case001_1120"
        and (
            not evidence_just_presented
            or evidence_dialogue is not None
        )
        and plan.can_call_llm
    ):
        emotion = derive_npc_emotional_state(
            query,
            state=state,
            character_id=character_id,
            history=rag_result.history,
            evidence_just_presented=evidence_turn,
        )

    if plan.can_call_llm:
        context = plan.authorized_context

        if context is None:
            raise RuntimeError(
                "검증된 RAG 컨텍스트가 없습니다."
            )

        # 기존 검증된 대화 이력 연결
        contextual_plan = build_contextual_npc_reply_plan(
            plan,
            rag_result.history,
            current_revision=state.revision,
        )

        reaction_prompt = build_npc_reaction_prompt(
            query,
            character_id=character_id,
            state=state,
            history=rag_result.history,
            evidence_just_presented=evidence_just_presented,
        )

        if len(contextual_plan.messages) != 2:
            raise ValueError(
                "NPC 메시지 형식이 올바르지 않습니다."
            )

        system_message, user_message = (
            contextual_plan.messages
        )

        if (
            system_message.get("role") != "system"
            or user_message.get("role") != "user"
        ):
            raise ValueError(
                "NPC 메시지 역할이 올바르지 않습니다."
            )

        # Apply expanded persona guidance only after RAG authorization.
        persona_suffix = ""

        if state.content_version == "case001_1120":
            persona_suffix = "\n\n" + build_dynamic_npc_prompt(
                state=state,
                character_id=character_id,
            )

        intent_suffix = ""

        if state.content_version == "case001_1120":
            intent_suffix = "\n\n" + build_npc_intent_prompt(
                query,
                evidence_just_presented=evidence_turn,
            )

        evidence_suffix = ""

        if evidence_dialogue is not None:
            evidence_suffix = (
                "\n\n"
                + build_evidence_dialogue_prompt(
                    evidence_dialogue,
                    context,
                )
            )

        contextual_plan = replace(
            contextual_plan,
            messages=(
                {
                    **system_message,
                    "content": (
                        system_message["content"]
                        + "\n\n"
                        + reaction_prompt
                        + persona_suffix
                        + intent_suffix
                        + evidence_suffix
                        + (
                            "\n\n" + build_npc_emotion_prompt(emotion)
                            if emotion is not None
                            else ""
                        )
                    ),
                },
                user_message,
            ),
        )

        # Reuse only a currently authorized, exact matching reply.
        cached_output = None

        if (
            state.content_version == "case001_1120"
            and not evidence_turn
        ):
            cached_output = build_revalidated_repeat_output(
                query,
                rag_result.history,
                current_revision=state.revision,
                context=context,
            )

        selected_generate = generate

        if cached_output is not None:
            # Cached output passes the same guard as model output.
            def replay_verified_quotes(_messages):
                return cached_output

            selected_generate = replay_verified_quotes

        # 기존 RAG 원문 및 출처 검증 유지
        reply = run_grounded_npc_response(
            contextual_plan,
            context,
            generate=selected_generate,
            **(
                {"retry_empty_quotes": False}
                if state.content_version == "case001_1120"
                else {}
            ),
        )

    else:
        # 승인된 근거가 없으면 LLM을 호출하지 않음
        if (
            plan.fallback_reply != FALLBACK_REPLY
            or plan.messages
            or plan.source_ids
            or plan.authorized_context is not None
        ):
            raise ValueError(
                "차단된 NPC 응답 계획이 올바르지 않습니다."
            )

        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

    # ==================================================
    # 5. 반복 인용 응답 처리
    # ==================================================

    # 서로 다른 질문에 같은 인용문이 반복되는 경우
    # 기존 정책대로 fallback으로 처리
    if (
        reply.grounded
        and not evidence_just_presented
        and any(
            previous.npc_message == reply.text
            and previous.user_message.strip() != query.strip()
            for previous in rag_result.history[-4:]
        )
    ):
        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )

    # ==================================================
    # 6. GameState 및 NPC 상태 재검증
    # ==================================================

    if state.revision != initial_revision:
        raise RuntimeError(
            "대화 처리 중 GameState가 변경됐습니다."
        )

    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError(
            "대화 처리 중 NPC가 변경됐습니다."
        )

    # ==================================================
    # 7. 자연스러운 NPC 말풍선 생성
    # ==================================================

    display_text = reply.text

    if reply.grounded:
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
            **(
                {
                    "expanded_persona": True,
                    **(
                        {"evidence_dialogue": evidence_dialogue}
                        if evidence_dialogue is not None
                        else {}
                    ),
                    **(
                        {"emotion": emotion}
                        if emotion is not None
                        else {}
                    ),
                }
                if state.content_version == "case001_1120"
                else {}
            ),
        )

    # ==================================================
    # 8. 검증된 NPC 응답 저장
    # ==================================================

    # A rejected display must never be recorded as a successful
    # disclosure or become an authorized conversation memory.
    if reply.grounded and display_text == FALLBACK_REPLY:
        reply = NPCGroundedReply(
            text=FALLBACK_REPLY,
            source_ids=(),
            grounded=False,
        )
        display_text = FALLBACK_REPLY

    # Keep canonical quotes for memory validation.
    # Persist presentation separately for expanded grounded turns.
    exchange = session_store.append_verified_exchange(
        state,
        character_id,
        user_message=query,
        reply=reply,
        **(
            {"display_text": display_text}
            if (
                state.content_version == "case001_1120"
                and reply.grounded
            )
            else {}
        ),
    )

    return NPCChatTurn(
        character_id=character_id,
        reply=reply,
        exchange=exchange,
        display_text=display_text,
    )
