"""Issue #23 - NPC RAG, Ollama, 출력 검증 및 세션 저장 통합."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from crimescene.chat.llm_client import generate_npc_json
from crimescene.chat.npc_history_context import (
    build_contextual_npc_reply_plan,
)
from crimescene.chat.npc_rag_service import (
    NPCRAGResources,
    prepare_npc_chat_rag,
)
from crimescene.chat.npc_session import (
    NPCExchange,
    NPCSessionStore,
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
    """검증 후 저장까지 완료한 NPC 대화 결과."""

    character_id: str
    reply: NPCGroundedReply
    exchange: NPCExchange


def run_npc_chat(
    query: str,
    *,
    state: GameState,
    session_store: NPCSessionStore,
    resources: NPCRAGResources,
    generate: Callable[[list[dict[str, str]]], str] = generate_npc_json,
    matched_topics: Iterable[str] = (),
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

    initial_revision = state.revision

    # 기존 NPC별 검색 및 접근 권한 검증
    rag_result = prepare_npc_chat_rag(
        query,
        state=state,
        session_store=session_store,
        resources=resources,
        matched_topics=matched_topics,
    )

    character_id = rag_result.character_id
    plan = rag_result.reply_plan

    if not isinstance(plan, NPCReplyPlan):
        raise TypeError("NPCReplyPlan이 필요합니다.")

    if plan.can_call_llm:
        # 접근 검증된 근거가 없으면 LLM을 호출하지 않는다.
        context = plan.authorized_context

        if context is None:
            raise RuntimeError("검증된 RAG 컨텍스트가 없습니다.")

        # 현재 NPC의 대화 기록만 컨텍스트에 추가한다.
        contextual_plan = build_contextual_npc_reply_plan(
            plan,
            rag_result.history,
            current_revision=state.revision,
        )

        # 현재 승인된 RAG 원문으로 최종 출력을 다시 검증한다.
        reply = run_grounded_npc_response(
            contextual_plan,
            context,
            generate=generate,
        )
    else:
        # 비승인 응답 계획은 고정 fallback만 허용한다.
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

    # LLM 호출 중 발생한 게임 상태 변경을 감지한다.
    if state.revision != initial_revision:
        raise RuntimeError("대화 처리 중 GameState가 변경됐습니다.")

    # NPC가 전환됐다면 이전 NPC의 답변을 저장하지 않는다.
    if session_store.get_active_npc(state) != character_id:
        raise RuntimeError("대화 처리 중 NPC가 변경됐습니다.")

    # 기존 세션 매니저의 검증 및 저장 기능을 재사용한다.
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
    )
