"""Issue #24 - CASE-001 실제 데이터 기반 NPC 접근 보안 검증.

실제 사건 원본과 RAG 접근 정책을 사용한다.
LLM, Qdrant 서버, 게임 DB를 변경하지 않는다.
"""

from pathlib import Path
from uuid import uuid4

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.retriever.authorized_multisource_context import (
    build_authorized_multisource_context,
)
from crimescene.retriever.multisource_rrf import FusedSearchCandidate
from crimescene.retriever.npc_presearch_access import (
    build_authorized_npc_point_ids,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import load_player_documents
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.npc_access import (
    NPCKnowledgeCardV71,
    select_authorized_npc_cards,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import EvidenceState, GameState
from crimescene.trigger.case001_dialogue import build_case001_recipients
from crimescene.trigger.evidence_presentation import (
    record_evidence_presentation,
)

DATA_ROOT = Path(__file__).resolve().parents[2] / ".local" / "case001_v7_1"


def find_unique_file(paths: list[Path], name: str) -> Path:
    """검증 대상 원본 파일이 정확히 하나인지 확인한다."""

    if len(paths) != 1:
        raise FileNotFoundError(f"{name} 파일은 정확히 하나여야 합니다: {len(paths)}개")

    return paths[0]


def make_state(
    npc_id: str,
    *,
    evidence_id: str | None = None,
) -> GameState:
    """증거 조건별 접근 검증에 사용할 GameState."""

    evidence = {}

    if evidence_id is not None:
        evidence[evidence_id] = EvidenceState(stage="found")

    return GameState(
        case_id="CASE-001",
        session_id=f"ISSUE24-SECURITY-{uuid4().hex}",
        unlocked_characters=[npc_id],
        evidence=evidence,
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def main() -> None:
    # ==================================================
    # 1. CASE-001 실제 원본 로딩
    # ==================================================

    character_path = find_unique_file(
        list(DATA_ROOT.glob("*/data/characters.json")),
        "characters.json",
    )

    evidence_path = find_unique_file(
        list(DATA_ROOT.rglob("evidence_rules.json")),
        "evidence_rules.json",
    )

    data_dir = character_path.parent

    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    policies = load_access_policies(data_dir / "access_policies.json")

    evidence_rules = load_evidence_rules(evidence_path)

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    records = load_case001_hybrid_records(data_dir)

    evaluator = PolicyEvaluator(policies)

    recipients = build_case001_recipients(
        policies=policies,
        npc_cards=cards,
        evidence_rules=evidence_rules,
    )

    # ==================================================
    # 2. 원본 개수 및 무결성 검증
    # ==================================================

    counts = (
        len(cards),
        len(policies),
        len(evidence_rules),
        len(records),
    )

    expected_counts = (88, 153, 10, 116)

    if counts != expected_counts:
        raise AssertionError(f"CASE-001 데이터 개수 불일치: {counts}")

    card_by_id = {}

    for raw_card in cards:
        card = NPCKnowledgeCardV71.model_validate(raw_card)

        if card.id in card_by_id:
            raise AssertionError("NPC 카드 ID가 중복됐습니다.")

        card_by_id[card.id] = card

    npc_records = [
        record for record in records if record.chunk.source_type == "npc_knowledge"
    ]

    record_card_ids = {record.chunk.source_id for record in npc_records}

    if record_card_ids != set(card_by_id):
        raise AssertionError("NPC 카드와 RAG 청크의 원본 ID가 일치하지 않습니다.")

    print("[PASS] CASE-001 원본 무결성")

    # ==================================================
    # 3. 검색 전 권한 검증
    # ==================================================

    def check_access(
        npc_id: str,
        state: GameState,
    ) -> set[str]:
        """승인 카드와 Qdrant 검색 허용 UUID를 대조한다."""

        authorized = select_authorized_npc_cards(
            cards,
            state,
            evaluator,
            active_character_id=npc_id,
        )

        authorized_ids = {card.card_id for card in authorized}

        point_ids = build_authorized_npc_point_ids(
            trusted_records=records,
            npc_cards=cards,
            state=state,
            evaluator=evaluator,
            active_character_id=npc_id,
        )

        expected_points = {
            record.chunk.point_id
            for record in npc_records
            if (
                record.chunk.character_id == npc_id
                and record.chunk.source_id in authorized_ids
            )
        }

        if point_ids != expected_points:
            raise AssertionError(f"{npc_id}: 승인되지 않은 RAG 청크가 포함됐습니다.")

        return authorized_ids

    # ==================================================
    # 4. NPC 10명 보안 시나리오
    # ==================================================

    denied_contexts = 0
    verified_presentations = 0

    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        initial = make_state(npc_id)

        # 초기 공개 가능 카드
        baseline = check_access(
            npc_id,
            initial,
        )

        # ----------------------------------------------
        # A. 미해금 NPC 접근 차단
        # ----------------------------------------------

        locked = initial.model_copy(
            update={
                "unlocked_characters": [],
            }
        )

        if check_access(npc_id, locked):
            raise AssertionError(f"{npc_id}: 미해금 NPC 정보가 공개됐습니다.")

        # ----------------------------------------------
        # B. 잠긴 RAG 원문 강제 주입 테스트
        # ----------------------------------------------

        for record in npc_records:
            chunk = record.chunk

            if chunk.character_id != npc_id:
                continue

            if chunk.source_id in baseline:
                continue

            # 접근할 수 없는 실제 청크를
            # 검색 후보에 강제로 주입한다.
            candidate = FusedSearchCandidate(
                kind="chunk",
                item_id=chunk.point_id,
                score=1.0,
                methods=("dense",),
            )

            graph_context = QuestionGraphContext(
                character_id=npc_id,
                matched_entity_ids=(),
                relations=(),
                evidence=(),
            )

            authorized_context = build_authorized_multisource_context(
                [candidate],
                trusted_records=records,
                documents=documents,
                npc_cards=cards,
                graph_context=graph_context,
                registry=(),
                trusted_edges=(),
                evidence_rules=evidence_rules,
                state=initial,
                evaluator=evaluator,
                active_character_id=npc_id,
            )

            if authorized_context.items:
                raise AssertionError(
                    f"{npc_id}: 잠긴 지식이 최종 RAG 검증을 통과했습니다."
                )

            denied_contexts += 1

        # ----------------------------------------------
        # C. 증거 10개에 대한 제시 조건 검증
        # ----------------------------------------------

        for evidence_id in evidence_rules:
            # 증거를 수집하지 않은 상태에서
            # 제시 기록만 위조해도 해금되면 안 된다.
            forged_state = initial.model_copy(
                update={
                    "presented": {
                        npc_id: [evidence_id],
                    }
                }
            )

            forged_cards = check_access(
                npc_id,
                forged_state,
            )

            if forged_cards != baseline:
                raise AssertionError(
                    f"{npc_id}: {evidence_id} 위조 제시로 정보가 해금됐습니다."
                )

            # ------------------------------------------
            # D. 증거를 실제 수집한 상태
            # ------------------------------------------

            collected = make_state(
                npc_id,
                evidence_id=evidence_id,
            )

            check_access(
                npc_id,
                collected,
            )

            # 제시 가능 NPC는 실제 정책으로 결정
            allowed_npcs = recipients.get(
                evidence_id,
                frozenset(),
            )

            if npc_id not in allowed_npcs:
                continue

            # ------------------------------------------
            # E. 실제 증거 제시
            # ------------------------------------------

            presented = record_evidence_presentation(
                state=collected,
                active_character_id=npc_id,
                evidence_id=evidence_id,
                evidence_rules=evidence_rules,
                allowed_recipients=recipients,
            )

            if not presented.created:
                raise AssertionError("정상 증거 제시가 기록되지 않았습니다.")

            if presented.state.revision != 1:
                raise AssertionError("GameState revision이 올바르지 않습니다.")

            # 변경된 상태에서도 RAG 접근 정책 검사
            check_access(
                npc_id,
                presented.state,
            )

            # ------------------------------------------
            # F. 중복 증거 제시 차단
            # ------------------------------------------

            repeated = record_evidence_presentation(
                state=presented.state,
                active_character_id=npc_id,
                evidence_id=evidence_id,
                evidence_rules=evidence_rules,
                allowed_recipients=recipients,
            )

            if repeated.created:
                raise AssertionError("중복 증거가 새로 기록됐습니다.")

            if repeated.state.revision != 1:
                raise AssertionError("중복 제시로 revision이 증가했습니다.")

            verified_presentations += 1

    # ==================================================
    # 5. 검증 결과
    # ==================================================

    print("[PASS] NPC 10명 접근 권한 격리")

    print(
        "[PASS] 미승인 RAG 컨텍스트 차단:",
        denied_contexts,
    )

    print("[PASS] 미수집 증거 제시 위조 차단: 100개 조합")

    print(
        "[PASS] 정상 증거 제시 및 중복 방지:",
        verified_presentations,
    )

    if verified_presentations == 0:
        raise AssertionError(
            "증거 제시 매핑이 없습니다. "
            "실제 CASE-001 정책과 제시 규칙을 확인해야 합니다."
        )

    print()
    print("=" * 60)
    print("ISSUE #24 - CASE-001 SECURITY AUDIT PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
