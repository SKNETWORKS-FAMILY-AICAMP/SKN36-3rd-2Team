"""GameState 기반 Neo4j 증거 보유 관계 검색."""

from collections.abc import Mapping
from dataclasses import dataclass

from neo4j import Driver

from crimescene.retriever.graph_search import CHARACTER_IDS
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState

CASE_ID = "CASE-001"

EVIDENCE_QUERY = """
MATCH (e:CaseEntity:Evidence {
    case_id: $case_id
})-[r:EVIDENCE_HOLDER {
    case_id: $case_id
}]->(holder:CaseEntity:Person {
    case_id: $case_id,
    entity_id: $character_id
})
WHERE e.entity_id IN $evidence_ids
AND r.evidence_id = e.entity_id
AND r.access_scope = 'collected_evidence'
AND r.source = 'evidence_rules.holder'
RETURN DISTINCT
    e.entity_id AS evidence_id,
    holder.entity_id AS holder_id
ORDER BY evidence_id
LIMIT $top_k
"""


@dataclass(frozen=True)
class EvidenceGraphResult:
    """권한 검증이 완료된 증거 관계."""

    evidence_id: str
    holder_id: str
    relation: str = "EVIDENCE_HOLDER"


def search_character_evidence(
    driver: Driver,
    character_id: str,
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule],
    *,
    top_k: int = 10,
) -> list[EvidenceGraphResult]:
    """NPC와 연결된 수집 완료 증거만 검색한다."""

    # 1. 입력값 검증
    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= 100:
        raise ValueError("top_k는 1~100 사이여야 합니다.")

    # 2. NPC 해금 검증
    if character_id not in state.unlocked_characters:
        return []

    # 3. 서버에서 관리하는 증거 규칙 확인
    allowed_ids = set()

    for evidence_id, rule in evidence_rules.items():
        if not isinstance(rule, EvidenceRule):
            raise TypeError("검증되지 않은 증거 규칙입니다.")

        # 현재 인물과 관련된 증거만 선택
        if rule.holder != character_id:
            continue

        # 실제 증거 수집 여부 확인
        evidence_state = state.evidence.get(evidence_id)

        if evidence_state is None:
            continue

        if evidence_state.stage not in PolicyEvaluator.VALID_EVIDENCE_STAGES:
            continue

        allowed_ids.add(evidence_id)

    # 수집된 증거가 없으면 DB 검색하지 않음
    if not allowed_ids:
        return []

    # 4. Neo4j 검색
    with driver.session() as session:
        records = session.run(
            EVIDENCE_QUERY,
            case_id=state.case_id,
            character_id=character_id,
            evidence_ids=sorted(allowed_ids),
            top_k=top_k,
        ).data()

    # 5. 검색 결과 재검증
    results = []
    seen_ids = set()

    for record in records:
        evidence_id = record.get("evidence_id")
        holder_id = record.get("holder_id")

        if not isinstance(evidence_id, str):
            raise TypeError("증거 ID 형식이 올바르지 않습니다.")

        if not isinstance(holder_id, str):
            raise TypeError("보유자 ID 형식이 올바르지 않습니다.")

        # 서버가 승인하지 않은 증거 차단
        if evidence_id not in allowed_ids:
            raise ValueError("승인되지 않은 증거가 검색됐습니다.")

        # 인물 불일치 차단
        if holder_id != character_id:
            raise ValueError("증거 보유자 정보가 일치하지 않습니다.")

        if evidence_id in seen_ids:
            continue

        seen_ids.add(evidence_id)

        results.append(
            EvidenceGraphResult(
                evidence_id=evidence_id,
                holder_id=holder_id,
            )
        )

        if len(results) >= top_k:
            break

    return results
