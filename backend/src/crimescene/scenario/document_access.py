import hashlib
from collections.abc import Iterable

from crimescene.scenario.e26_section_policy import (
    can_access_e26_section_for_state,
)

from pydantic import BaseModel, ConfigDict, Field

from crimescene.scenario.policy_evaluator import (
    PolicyEvaluator,
    matches_ending_requirement,
)
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.game_state import GameState


def can_access_published_e26_document(
    state: GameState,
    document: PlayerDocument,
    evaluator: PolicyEvaluator | None,
) -> bool:
    """Accept only the server-published section A document."""

    if not isinstance(evaluator, PolicyEvaluator):
        return False

    if (
        document.doc_id != "DOC-1120-E26-A"
        or document.policy_id != "POL-1120-DOC-E26-A"
        or document.case_id != "CASE-001"
        or document.content_version != "case001_1120"
        or document.state_version != "case001_1120"
        or document.source_evidence_ids != ["E26"]
        or document.family != "evidence"
        or document.access_scope != "collected_evidence"
        or document.required_evidence != ["E20", "E26"]
        or set(document.required_flags) != {
            "ACT_AUDIT_LOG_ACCESS_VERIFIED"
        }
        or document.required_presentations
        or document.required_ending is not None
        or document.protected_fact_ids
        or document.content_hash != hashlib.sha256(
            document.body.encode("utf-8")
        ).hexdigest()
        or document.search_text != (
            document.title + chr(10) + document.body
        )
    ):
        return False

    # Only the release-owned evaluator may authorize this policy.
    approved = evaluator.is_allowed(
        document.policy_id,
        state,
    )

    return can_access_e26_section_for_state(
        "A",
        state,
        section_a_approved=approved,
    )


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
        if "E30" in document.source_evidence_ids:
            continue

        if (
            "E26" in document.source_evidence_ids
            and not can_access_published_e26_document(
                state,
                document,
                evaluator,
            )
        ):
            continue

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
        if not matches_ending_requirement(document.required_ending, state):
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
