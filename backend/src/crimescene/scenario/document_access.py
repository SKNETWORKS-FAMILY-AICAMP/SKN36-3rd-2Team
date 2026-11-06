from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState


class AuthorizedPlayerDocument(BaseModel):
    """접근 검사를 통과한 플레이어용 문서."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


def select_authorized_player_documents(
    documents: Iterable[PlayerDocument],
    state: GameState,
    evaluator: PolicyEvaluator,
    *,
    matched_topics: Iterable[str] = (),
) -> list[AuthorizedPlayerDocument]:
    """현재 게임 상태에서 접근 가능한 플레이어 문서만 반환한다."""

    allowed_documents: list[AuthorizedPlayerDocument] = []

    topics = tuple(matched_topics)

    collected_evidence = {
        evidence_id
        for evidence_id, evidence_state in state.evidence.items()
        if evidence_state.stage in {"found", "resolved"}
    }

    for document in documents:
        # 1. 다른 사건의 문서 차단
        if document.case_id != state.case_id:
            continue

        # 2. 플레이어 공개용 문서만 허용
        if document.access_scope not in {
            "collected_evidence",
            "conditional_record",
        }:
            continue

        # 3. 등록된 접근 정책 검사
        if not evaluator.is_allowed(
            document.policy_id,
            state,
            matched_topics=topics,
        ):
            continue

        # 4. 문서 자체에 명시된 증거 조건도 검사
        if not set(document.required_evidence).issubset(collected_evidence):
            continue

        # 5. 게임 플래그 검사
        if not set(document.required_flags).issubset(state.flags):
            continue

        # 6. 문서별 엔딩 조건 검사
        if (
            document.required_ending is not None
            and document.required_ending != state.outcome
        ):
            continue

        # 7. 문서별 증거 제시 조건 검사
        presentations_valid = True

        for presentation in document.required_presentations:
            npc_id, separator, evidence_id = presentation.partition(":")

            if (
                not separator
                or not npc_id
                or not evidence_id
                or evidence_id not in collected_evidence
                or evidence_id not in state.presented.get(npc_id, [])
            ):
                presentations_valid = False
                break

        if not presentations_valid:
            continue

        # 8. 승인된 문서의 공개용 필드만 반환
        allowed_documents.append(
            AuthorizedPlayerDocument(
                doc_id=document.doc_id,
                title=document.title,
                content=document.body,
            )
        )

    return allowed_documents
