"""DB-backed, bounded semantic dialogue recall."""

from crimescene.chat.npc_memory_recall import (
    RECALL_OPENERS,
    UNKNOWN_QUESTION_REPLY,
    build_memory_recall_reply,
)

from crimescene.chat.npc_semantic_router import (
    SemanticRoute,
    build_semantic_social_reply,
)

FIRST_PREFIX = "처음 대화요? "
LAST_PREFIX = "아까 대화요? "

NO_HISTORY = "아직 저와 나눈 이야기가 없어요."

UNKNOWN_HISTORY = (
    "정확히 어떤 이야기였는지 다시 짚어 주시겠어요?"
)

SOCIAL_MEMORY_SUMMARIES = {
    SemanticRoute.GREETING: "제게 인사하셨죠.",
    SemanticRoute.TALK: "잠깐 이야기할 수 있냐고 물으셨죠.",
    SemanticRoute.THANKS: "감사 인사를 하셨죠.",
    SemanticRoute.FAREWELL: "작별 인사를 하셨죠.",
    SemanticRoute.CHECK_IN: "제 안부를 물으셨죠.",
    SemanticRoute.PERSONAL: "개인적인 취향을 물으셨죠.",
    SemanticRoute.PRESSURE: "제 반응에 대해 물으셨죠.",
}


def semantic_memory_kind(answer: str) -> str | None:

    if not isinstance(answer, str):
        return None

    if answer.startswith(FIRST_PREFIX):
        return "first"

    if answer.startswith(LAST_PREFIX):
        return "last"

    return None


def build_semantic_memory_reply(
    character_id: str,
    *,
    kind: str,
    previous_question: str | None,
    previous_revision: int | None,
    previous_answer: str | None,
    previous_source_ids,
    current_revision: int,
) -> str | None:

    if character_id not in RECALL_OPENERS:
        return None

    if kind not in {"first", "last"}:
        return None

    if (
        type(current_revision) is not int
        or current_revision < 0
    ):
        return None

    prefix = (
        FIRST_PREFIX
        if kind == "first"
        else LAST_PREFIX
    )

    if previous_question is None:

        if (
            previous_revision is not None
            or previous_answer is not None
            or previous_source_ids
        ):
            return None

        return prefix + NO_HISTORY

    if (
        not isinstance(previous_question, str)
        or not previous_question.strip()
        or type(previous_revision) is not int
        or not 0 <= previous_revision <= current_revision
    ):
        return None

    # 기존의 안전한 기억 요약기를 우선 재사용한다.
    old_reply = build_memory_recall_reply(
        character_id,
        "제가 아까 어떤 질문을 했는지 기억하세요?",
        previous_question=previous_question,
        previous_revision=previous_revision,
        current_revision=current_revision,
    )

    if old_reply is None:
        return None

    opener = RECALL_OPENERS[character_id] + " "

    if old_reply.startswith(opener):
        summary = old_reply[len(opener):]

        return prefix + summary

    # 의미 기반 일상 대화는 이전에 저장한 서버 소유
    # 응답과 비교하여 대화 종류를 복원한다.
    # 과거 사용자 입력과 사건 원문은 그대로 출력하지 않는다.
    if (
        old_reply == UNKNOWN_QUESTION_REPLY
        and not previous_source_ids
        and isinstance(previous_answer, str)
    ):
        matches = {
            summary
            for route, summary in SOCIAL_MEMORY_SUMMARIES.items()
            if build_semantic_social_reply(
                character_id, route
            ) == previous_answer
        }

        if len(matches) == 1:
            return prefix + next(iter(matches))

    return prefix + UNKNOWN_HISTORY


def build_semantic_memory_from_history(
    character_id: str,
    history,
    *,
    kind: str,
    current_revision: int,
) -> str | None:

    if kind not in {"first", "last"}:
        return None

    previous = (
        history[0 if kind == "first" else -1]
        if history else None
    )

    return build_semantic_memory_reply(
        character_id,
        kind=kind,
        previous_question=(
            previous.user_message
            if previous else None
        ),
        previous_revision=(
            previous.state_revision
            if previous else None
        ),
        previous_answer=(
            previous.npc_message
            if previous else None
        ),
        previous_source_ids=(
            previous.source_ids
            if previous else ()
        ),
        current_revision=current_revision,
    )
