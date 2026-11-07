"""GameState 기반 Neo4j 관계 검색."""

from collections.abc import Sequence
from dataclasses import dataclass

from neo4j import Driver

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

GRAPH_QUERY = """
MATCH (person:CaseEntity {
    case_id: $case_id,
    entity_id: $character_id
})-[r:CASE_RELATION]-(neighbor:CaseEntity {
    case_id: $case_id
})
WHERE r.case_id = $case_id
RETURN DISTINCT r.edge_id AS edge_id
ORDER BY edge_id
LIMIT $candidate_limit
"""

# CASE-001 등장인물 ID
CHARACTER_IDS = frozenset(f"C{i:02d}" for i in range(1, 11))
# CASE-001 증거 ID
EVIDENCE_IDS = frozenset(f"E{i:02d}" for i in range(1, 11))


@dataclass(frozen=True)
class GraphSearchResult:
    """접근 권한 검증을 완료한 관계 정보."""

    edge_id: str
    source_id: str
    target_id: str
    neighbor_id: str
    relation: str
    truth_status: str
    access_scope: str
    incident_year: int


def is_relation_visible(
    edge: RelationshipSourceEdge,
    state: GameState,
) -> bool:
    """현재 게임 상태에서 관계 공개 가능 여부를 검사한다."""

    # 1. 사건 ID 검증
    if edge.case_id != state.case_id:
        return False

    # 2. 엔딩 전용 관계
    # 엔딩 조건이 정의되지 않은 경우 접근 차단
    if edge.access_scope == "ending_only" and not edge.required_ending:
        return False

    # 3. 조건부 관계
    # 공개 조건이 하나도 정의되지 않았다면 접근 차단
    if edge.access_scope == "conditional" and not any(
        (
            edge.required_evidence,
            edge.required_presentations,
            edge.required_flags,
            edge.required_ending,
        )
    ):
        return False

    # 4. 기존 접근 정책 엔진 재사용
    policy = AccessPolicy(
        required_evidence=edge.required_evidence,
        required_presentations=edge.required_presentations,
        required_flags=edge.required_flags,
        required_ending=edge.required_ending,
        required_topics=[],
        required_disclosed_cards=[],
        required_character=None,
    )

    evaluator = PolicyEvaluator({"POL-GRAPH": policy})

    # 5. GameState 기반 접근 권한 확인
    return evaluator.is_allowed(
        "POL-GRAPH",
        state,
    )


def search_character_relations(
    driver: Driver,
    character_id: str,
    state: GameState,
    trusted_edges: Sequence[RelationshipSourceEdge],
    *,
    top_k: int = 20,
) -> list[GraphSearchResult]:
    """특정 인물의 접근 가능한 관계를 검색한다.

    검색 과정:
        1. 입력값 및 GameState 검증
        2. NPC 해금 상태 확인
        3. 서버 원본 관계 데이터 검증
        4. Neo4j Cypher 검색
        5. 검색 결과와 원본 관계 비교
        6. GameState 기반 접근 권한 검증
        7. 미해금 NPC 관계 제거
        8. 최종 결과 반환

    보안 원칙:
        - Neo4j 검색 결과는 신뢰하지 않는다.
        - 관계 내용은 서버 원본 데이터에서 가져온다.
        - 관리자 전용 관계는 trusted_edges에 포함하지 않는다.
        - 미해금 NPC와 비공개 관계는 반환하지 않는다.
    """

    # --------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if not isinstance(character_id, str):
        raise TypeError("NPC ID는 문자열이어야 합니다.")

    if character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= 100:
        raise ValueError("top_k는 1~100 사이여야 합니다.")

    # --------------------------------------------------
    # 2. NPC 해금 상태 검증
    # --------------------------------------------------

    # 플레이어가 아직 해금하지 않은 NPC라면
    # Neo4j 검색 자체를 수행하지 않는다.
    if character_id not in state.unlocked_characters:
        return []

    # --------------------------------------------------
    # 3. 신뢰할 수 있는 원본 관계 데이터 구성
    # --------------------------------------------------

    trusted_by_id: dict[str, RelationshipSourceEdge] = {}

    for edge in trusted_edges:
        # Pydantic으로 검증된 관계 데이터만 허용
        if not isinstance(edge, RelationshipSourceEdge):
            raise TypeError("검증되지 않은 관계 데이터입니다.")

        # 사건 ID 불일치 차단
        if edge.case_id != state.case_id:
            raise ValueError("관계 사건 ID가 일치하지 않습니다.")

        # 동일 관계 ID 중복 차단
        if edge.edge_id in trusted_by_id:
            raise ValueError("중복된 관계 ID가 존재합니다.")

        trusted_by_id[edge.edge_id] = edge

    # --------------------------------------------------
    # 4. Neo4j 관계 검색
    # --------------------------------------------------

    # DB에서는 관계 ID만 조회한다.
    # 관계 내용 및 공개 조건은 서버 원본을 기준으로 검증한다.
    with driver.session() as session:
        records = session.run(
            GRAPH_QUERY,
            case_id=state.case_id,
            character_id=character_id,
            candidate_limit=1000,
        ).data()

    # --------------------------------------------------
    # 5. 검색 결과 검증
    # --------------------------------------------------

    results: list[GraphSearchResult] = []

    seen_ids: set[str] = set()

    for record in records:
        edge_id = record.get("edge_id")

        # 관계 ID 타입 검증
        if not isinstance(edge_id, str):
            raise TypeError("잘못된 관계 검색 결과입니다.")

        # 중복 검색 결과 제거
        if edge_id in seen_ids:
            continue

        seen_ids.add(edge_id)

        # 신뢰할 수 있는 원본 관계 조회
        edge = trusted_by_id.get(edge_id)

        # Neo4j에만 존재하는 관계는 차단
        if edge is None:
            raise ValueError("신뢰할 수 없는 관계 ID가 검색됐습니다.")

        # --------------------------------------------------
        # 6. 인물과 관계의 연결 여부 검증
        # --------------------------------------------------

        if character_id not in {
            edge.source_id,
            edge.target_id,
        }:
            raise ValueError("관계의 연결 정보가 일치하지 않습니다.")

        # --------------------------------------------------
        # 7. GameState 기반 접근 권한 검증
        # --------------------------------------------------

        if not is_relation_visible(edge, state):
            continue

        # --------------------------------------------------
        # 8. 연결된 상대 엔티티 확인
        # --------------------------------------------------

        neighbor_id = (
            edge.target_id if edge.source_id == character_id else edge.source_id
        )

        # --------------------------------------------------
        # 9. 미해금 NPC 관계 차단
        # --------------------------------------------------

        # 연결된 대상이 NPC라면 해금 상태를 확인한다.
        # 장소·사건·증거 등 NPC 이외의 엔티티는
        # 관계 자체의 접근 정책으로 공개 여부를 판단한다.
        if (
            neighbor_id in CHARACTER_IDS
            and neighbor_id not in state.unlocked_characters
        ):
            continue
        # 미수집 증거에 연결된 관계 차단
        if neighbor_id in EVIDENCE_IDS:
            evidence_state = state.evidence.get(neighbor_id)

            if (
                evidence_state is None
                or evidence_state.stage not in PolicyEvaluator.VALID_EVIDENCE_STAGES
            ):
                continue
        # --------------------------------------------------
        # 10. 최종 검색 결과 생성
        # --------------------------------------------------

        results.append(
            GraphSearchResult(
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                neighbor_id=neighbor_id,
                relation=edge.relation,
                truth_status=edge.truth_status,
                access_scope=edge.access_scope,
                incident_year=edge.incident_year,
            )
        )

        # --------------------------------------------------
        # 11. 검색 결과 개수 제한
        # --------------------------------------------------

        if len(results) >= top_k:
            break

    # --------------------------------------------------
    # 12. 접근 검증을 완료한 관계만 반환
    # --------------------------------------------------

    return results
