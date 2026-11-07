"""CASE-001 3중 Hybrid RAG 최종 접근 제어 및 컨텍스트 생성."""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from crimescene.ingest.hybrid_access import build_authorized_hybrid_context
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.retriever.graph_context_builder import build_graph_rag_context
from crimescene.retriever.graph_search import CHARACTER_IDS
from crimescene.retriever.multisource_rrf import (
    CandidateKind,
    FusedSearchCandidate,
    SearchMethod,
)
from crimescene.retriever.query_graph_retriever import QuestionGraphContext
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge

CASE_ID = "CASE-001"


@dataclass(frozen=True, slots=True)
class AuthorizedMultisourceItem:
    """최종 권한 검증을 통과한 검색 근거."""

    kind: CandidateKind
    item_id: str
    source_id: str
    score: float
    methods: tuple[SearchMethod, ...]
    content: str
    truth_status: str | None


@dataclass(frozen=True, slots=True)
class AuthorizedMultisourceContext:
    """LLM에 전달할 수 있도록 검증한 검색 컨텍스트."""

    items: tuple[AuthorizedMultisourceItem, ...]
    text: str


def _validate_candidates(
    candidates: Sequence[FusedSearchCandidate],
) -> list[FusedSearchCandidate]:
    """통합 검색 후보의 구조와 중복 여부를 검증한다."""

    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError("검색 후보는 시퀀스여야 합니다.")

    seen = set()

    for item in candidates:
        if not isinstance(item, FusedSearchCandidate):
            raise TypeError("통합 검색 후보 타입이 올바르지 않습니다.")

        if item.kind not in {"chunk", "relation", "evidence"}:
            raise ValueError("지원하지 않는 검색 후보 유형입니다.")

        if not isinstance(item.item_id, str) or not item.item_id.strip():
            raise ValueError("검색 후보 ID가 올바르지 않습니다.")

        if (
            isinstance(item.score, bool)
            or not isinstance(item.score, (int, float))
            or not math.isfinite(item.score)
            or item.score <= 0
        ):
            raise ValueError("검색 후보 점수가 올바르지 않습니다.")

        if not isinstance(item.methods, tuple) or not item.methods:
            raise ValueError("검색 출처가 올바르지 않습니다.")

        if len(item.methods) != len(set(item.methods)):
            raise ValueError("중복된 검색 출처입니다.")

        if item.kind == "chunk":
            if not set(item.methods) <= {"dense", "bm25"}:
                raise ValueError("문서 청크의 검색 출처가 올바르지 않습니다.")
        elif item.methods != ("graph",):
            raise ValueError("Graph 검색 출처가 올바르지 않습니다.")

        key = (item.kind, item.item_id)

        if key in seen:
            raise ValueError("중복된 통합 검색 후보입니다.")

        seen.add(key)

    return sorted(
        candidates,
        key=lambda item: (-item.score, item.kind, item.item_id),
    )


def _render_context(
    items: Sequence[AuthorizedMultisourceItem],
) -> str:
    """접근 검증된 근거를 LLM 참고 텍스트로 변환한다."""

    if not items:
        return "공개 가능한 검색 근거가 없습니다."

    lines = [
        "[MULTISOURCE_RAG_CONTEXT]",
        "다음은 접근 권한을 확인한 참고 자료입니다.",
        "목격 진술과 가설을 확정된 사실로 취급하지 마세요.",
        "자료에 없는 사실을 만들어내지 마세요.",
    ]

    for index, item in enumerate(items, start=1):
        lines.append(f"[SOURCE {index}] kind={item.kind} id={item.source_id}")
        lines.append(f"truth_status={item.truth_status or 'unspecified'}")
        lines.append(item.content)
        lines.append("[/SOURCE]")

    lines.append("[/MULTISOURCE_RAG_CONTEXT]")

    return "\n".join(lines)


def build_authorized_multisource_context(
    candidates: Sequence[FusedSearchCandidate],
    *,
    trusted_records: Iterable[HybridChunkRecord],
    documents: Iterable[PlayerDocument],
    npc_cards: Iterable[Mapping[str, object]],
    graph_context: QuestionGraphContext,
    registry: Sequence[Mapping[str, object]],
    trusted_edges: Sequence[RelationshipSourceEdge],
    evidence_rules: Mapping[str, EvidenceRule],
    state: GameState,
    evaluator: PolicyEvaluator,
    active_character_id: str,
    allowed_entity_ids: Iterable[str] = (),
    matched_topics: Iterable[str] = (),
    top_k: int = 10,
) -> AuthorizedMultisourceContext:
    """3중 RRF 결과를 권한 검증 후 LLM 컨텍스트로 변환한다.

    보안 원칙:
    - Qdrant UUID는 서버 원본과 대조한다.
    - NPC 지식 정책은 기존 검증 엔진을 사용한다.
    - Graph 관계는 원본 관계 및 GameState로 재검증한다.
    - 플레이어 문서를 NPC 지식으로 자동 사용하지 않는다.
    - Graph의 비공개 원문 ID는 전달하지 않는다.
    - Top-K는 권한 검증 이후 적용한다.
    """

    # 1. 게임 상태 및 입력 검증
    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if not isinstance(evaluator, PolicyEvaluator):
        raise TypeError("PolicyEvaluator가 필요합니다.")

    if active_character_id not in CHARACTER_IDS:
        raise ValueError("유효하지 않은 NPC ID입니다.")

    if not isinstance(graph_context, QuestionGraphContext):
        raise TypeError("QuestionGraphContext가 필요합니다.")

    if graph_context.character_id != active_character_id:
        raise ValueError("Graph 검색 대상 NPC가 일치하지 않습니다.")

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k는 정수여야 합니다.")

    if not 1 <= top_k <= 100:
        raise ValueError("top_k는 1~100 사이여야 합니다.")

    if isinstance(allowed_entity_ids, (str, bytes)):
        raise TypeError("허용 엔티티 목록 형식이 올바르지 않습니다.")

    ordered_candidates = _validate_candidates(candidates)

    empty = AuthorizedMultisourceContext(
        items=(),
        text="공개 가능한 검색 근거가 없습니다.",
    )

    # 현재 NPC가 잠겨 있으면 모든 근거 차단
    if active_character_id not in state.unlocked_characters:
        return empty

    # 2. 서버 신뢰 원본 확보
    records = list(trusted_records)
    all_documents = list(documents)
    all_cards = list(npc_cards)
    all_edges = list(trusted_edges)

    allowed_entities = tuple(allowed_entity_ids)
    topics = tuple(matched_topics)

    if any(not isinstance(value, str) for value in allowed_entities):
        raise TypeError("허용 엔티티 ID 형식이 올바르지 않습니다.")

    record_by_id = {}

    for record in records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("검증되지 않은 RAG 청크입니다.")

        if record.chunk.case_id != state.case_id:
            raise ValueError("RAG 청크 사건 ID가 일치하지 않습니다.")

        point_id = record.chunk.point_id

        if point_id in record_by_id:
            raise ValueError("중복된 신뢰 RAG 청크 UUID입니다.")

        record_by_id[point_id] = record

    relation_by_id = {}

    for relation in graph_context.relations:
        if relation.edge_id in relation_by_id:
            raise ValueError("중복된 Graph 관계 ID입니다.")

        relation_by_id[relation.edge_id] = relation

    evidence_by_id = {}

    for evidence in graph_context.evidence:
        if evidence.evidence_id in evidence_by_id:
            raise ValueError("중복된 Graph 증거 ID입니다.")

        evidence_by_id[evidence.evidence_id] = evidence

    # 3. RRF 순위를 유지하면서 권한 검증
    authorized = []

    for candidate in ordered_candidates:
        # ------------------------------------------
        # Qdrant 청크
        # ------------------------------------------
        if candidate.kind == "chunk":
            record = record_by_id.get(candidate.item_id)

            if record is None:
                raise ValueError("신뢰할 수 없는 Qdrant 후보 UUID입니다.")

            # NPC 대화에서는 현재 NPC의 지식만 허용
            if (
                record.chunk.source_type != "npc_knowledge"
                or record.chunk.character_id != active_character_id
            ):
                continue

            # 기존 원본·정책·supersedes 검증 재사용
            approved = build_authorized_hybrid_context(
                [record],
                documents=all_documents,
                npc_cards=all_cards,
                state=state,
                evaluator=evaluator,
                active_character_id=active_character_id,
                matched_topics=topics,
                trusted_records=records,
            )

            if not approved:
                continue

            if len(approved) != 1:
                raise ValueError("청크 접근 검증 결과가 올바르지 않습니다.")

            source = approved[0]

            authorized.append(
                AuthorizedMultisourceItem(
                    kind="chunk",
                    item_id=candidate.item_id,
                    source_id=source.source_id,
                    score=candidate.score,
                    methods=candidate.methods,
                    content=source.content,
                    truth_status=source.truth_status,
                )
            )

        # ------------------------------------------
        # Neo4j 관계·증거
        # ------------------------------------------
        else:
            if candidate.kind == "relation":
                relation = relation_by_id.get(candidate.item_id)

                if relation is None:
                    raise ValueError("신뢰할 수 없는 Graph 관계 ID입니다.")

                narrowed_graph = QuestionGraphContext(
                    character_id=active_character_id,
                    matched_entity_ids=graph_context.matched_entity_ids,
                    relations=(relation,),
                    evidence=(),
                )

                truth_status = relation.truth_status

            else:
                evidence = evidence_by_id.get(candidate.item_id)

                if evidence is None:
                    raise ValueError("신뢰할 수 없는 Graph 증거 ID입니다.")

                narrowed_graph = QuestionGraphContext(
                    character_id=active_character_id,
                    matched_entity_ids=graph_context.matched_entity_ids,
                    relations=(),
                    evidence=(evidence,),
                )

                truth_status = None

            # Graph 원본 및 GameState 권한 재검증
            graph_result = build_graph_rag_context(
                narrowed_graph,
                state=state,
                registry=registry,
                trusted_edges=all_edges,
                evidence_rules=evidence_rules,
                allowed_entity_ids=allowed_entities,
                # NPC 대화에 플레이어 문서 ID를 자동 공개하지 않음
                allowed_document_ids=(),
            )

            expected_ids = (
                graph_result.relation_ids
                if candidate.kind == "relation"
                else graph_result.evidence_ids
            )

            if candidate.item_id not in expected_ids:
                continue

            authorized.append(
                AuthorizedMultisourceItem(
                    kind=candidate.kind,
                    item_id=candidate.item_id,
                    source_id=candidate.item_id,
                    score=candidate.score,
                    methods=candidate.methods,
                    content=graph_result.text,
                    truth_status=truth_status,
                )
            )

        # 권한 검증 후 Top-K
        if len(authorized) >= top_k:
            break

    return AuthorizedMultisourceContext(
        items=tuple(authorized),
        text=_render_context(authorized),
    )
