"""CASE-001 Qdrant + Neo4j 통합 데이터 적재 파이프라인."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from crimescene.db.ingest_integrity import validate_qdrant_records
from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.db.neo4j_sync import (
    Neo4jSyncPlan,
    build_expected_snapshot,
    build_sync_plan,
    find_source,
    read_database_snapshot,
)
from crimescene.db.neo4j_sync_apply import apply_neo4j_snapshot
from crimescene.db.qdrant_sync import (
    QdrantSyncPlan,
    sync_qdrant_records,
)
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)
from crimescene.scenario.loaders.relationship_loader import (
    load_relationship_edges,
)
from crimescene.scenario.source_timeline import load_source_timeline
from crimescene.settings import settings


@dataclass(frozen=True)
class PipelineSources:
    """검증된 CASE-001 원본 데이터."""

    records: tuple[HybridChunkRecord, ...]
    document_ids: frozenset[str]
    npc_card_ids: frozenset[str]
    policy_ids: frozenset[str]
    graph_snapshot: dict


@dataclass(frozen=True)
class PipelinePlan:
    """두 DB의 변경사항."""

    qdrant: QdrantSyncPlan
    neo4j: Neo4jSyncPlan

    @property
    def total_changes(self) -> int:
        return self.qdrant.total_changes + self.neo4j.total_changes

    @property
    def total_deletions(self) -> int:
        qdrant_deletions = len(self.qdrant.deleted)

        neo4j_deletions = sum(len(delta.deleted) for delta in self.neo4j.areas.values())

        return qdrant_deletions + neo4j_deletions


def load_pipeline_sources(root: Path) -> PipelineSources:
    """CASE-001 실제 원본을 읽고 무결성을 검증한다."""

    root = root.resolve()

    if not root.is_dir():
        raise FileNotFoundError(f"CASE-001 원본 폴더가 없습니다: {root}")

    # --------------------------------------------------------
    # 1. Qdrant 원본
    # --------------------------------------------------------

    policy_path = find_source(
        root,
        "access_policies.json",
    )

    data_dir = policy_path.parent

    policies = load_access_policies(policy_path)

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    records = load_case001_hybrid_records(data_dir)

    document_ids = frozenset(document.doc_id for document in documents)

    npc_card_ids = frozenset(card["id"] for card in cards)

    policy_ids = frozenset(policies)

    vector_report = validate_qdrant_records(
        records,
        document_ids=document_ids,
        npc_card_ids=npc_card_ids,
        valid_policy_ids=policy_ids,
    )

    # 일부 원본이 청킹에서 누락되지 않았는지 확인
    expected_source_count = len(document_ids) + len(npc_card_ids)

    if vector_report.source_count != expected_source_count:
        raise ValueError("Qdrant 원본 개수와 청킹 결과가 일치하지 않습니다.")

    # --------------------------------------------------------
    # 2. Neo4j 원본
    # --------------------------------------------------------

    entities = load_entity_registry(find_source(root, "entity_registry.json"))

    relationships = load_relationship_edges(
        find_source(root, "relationship_edges_source.json")
    )

    evidence_rules = load_evidence_rules(find_source(root, "evidence_rules.json"))

    events = load_source_timeline(find_source(root, "timeline_events.json"))

    # 내부에서 Neo4j 무결성 검사 수행
    graph_snapshot = build_expected_snapshot(
        entities,
        relationships,
        evidence_rules,
        events,
    )

    return PipelineSources(
        records=tuple(records),
        document_ids=document_ids,
        npc_card_ids=npc_card_ids,
        policy_ids=policy_ids,
        graph_snapshot=graph_snapshot,
    )


def inspect_pipeline(
    sources: PipelineSources,
    *,
    qdrant_client: QdrantClient,
    neo4j_driver,
    embedder: OllamaEmbedder,
) -> PipelinePlan:
    """두 DB를 읽기 전용으로 검사한다."""

    qdrant_plan = sync_qdrant_records(
        sources.records,
        client=qdrant_client,
        embedder=embedder,
        document_ids=sources.document_ids,
        npc_card_ids=sources.npc_card_ids,
        valid_policy_ids=sources.policy_ids,
        dry_run=True,
    )

    actual_graph = read_database_snapshot(neo4j_driver)

    neo4j_plan = build_sync_plan(
        sources.graph_snapshot,
        actual_graph,
    )

    return PipelinePlan(
        qdrant=qdrant_plan,
        neo4j=neo4j_plan,
    )


def run_pipeline(
    sources: PipelineSources,
    *,
    qdrant_client: QdrantClient,
    neo4j_driver,
    embedder: OllamaEmbedder,
    apply: bool = False,
    allow_delete: bool = False,
) -> PipelinePlan:
    """두 DB의 변경사항을 검사하고 필요하면 동기화한다."""

    if not isinstance(apply, bool):
        raise TypeError("apply는 bool이어야 합니다.")

    if not isinstance(allow_delete, bool):
        raise TypeError("allow_delete는 bool이어야 합니다.")

    # --------------------------------------------------------
    # 1. 두 DB 모두 사전 검사
    # --------------------------------------------------------

    plan = inspect_pipeline(
        sources,
        qdrant_client=qdrant_client,
        neo4j_driver=neo4j_driver,
        embedder=embedder,
    )

    # 기본값: Dry Run
    if not apply:
        return plan

    # 관리자 원본이 포함되므로 개발 환경에서만 허용
    if settings.app_env.lower() != "development":
        raise RuntimeError("통합 적재는 로컬 개발 환경에서만 허용됩니다.")

    # 두 DB의 삭제 대상을 적재 전에 함께 확인
    if plan.total_deletions and not allow_delete:
        raise ValueError(
            f"삭제 대상 {plan.total_deletions}건이 있습니다. "
            "--allow-delete 옵션이 필요합니다."
        )

    # 변경사항이 없다면 쓰기 작업 생략
    if plan.total_changes == 0:
        return plan

    # --------------------------------------------------------
    # 2. Qdrant 동기화
    # --------------------------------------------------------

    if plan.qdrant.total_changes:
        print("[APPLY] Qdrant synchronization started")

        sync_qdrant_records(
            sources.records,
            client=qdrant_client,
            embedder=embedder,
            document_ids=sources.document_ids,
            npc_card_ids=sources.npc_card_ids,
            valid_policy_ids=sources.policy_ids,
            dry_run=False,
            allow_delete=allow_delete,
        )

        print("[PASS] Qdrant synchronization")

    # --------------------------------------------------------
    # 3. Neo4j 동기화
    # --------------------------------------------------------

    if plan.neo4j.total_changes:
        print("[APPLY] Neo4j synchronization started")

        apply_neo4j_snapshot(
            neo4j_driver,
            sources.graph_snapshot,
            allow_delete=allow_delete,
        )

        print("[PASS] Neo4j synchronization")

    # --------------------------------------------------------
    # 4. 최종 무결성 재검증
    # --------------------------------------------------------

    final_plan = inspect_pipeline(
        sources,
        qdrant_client=qdrant_client,
        neo4j_driver=neo4j_driver,
        embedder=embedder,
    )

    if final_plan.total_changes:
        raise RuntimeError(
            "통합 적재 후 데이터 불일치가 남아 있습니다. "
            f"남은 변경사항: {final_plan.total_changes}건"
        )

    print("[PASS] Final database integrity")

    # 최초 변경 내역 반환
    return plan


def print_pipeline_plan(plan: PipelinePlan) -> None:
    """관리자 원본 내용을 노출하지 않고 변경 건수만 출력한다."""

    qdrant = plan.qdrant

    print("=" * 65)
    print("CASE-001 DATA PIPELINE")
    print("=" * 65)

    print("\n[QDRANT]")
    print(f"Added: {len(qdrant.added)}")
    print(f"Updated: {len(qdrant.updated)}")
    print(f"Unchanged: {len(qdrant.unchanged)}")
    print(f"Deleted: {len(qdrant.deleted)}")

    print("\n[NEO4J]")

    print(f"{'AREA':<20}{'ADD':>8}{'UPDATE':>10}{'DELETE':>10}")

    for area, delta in plan.neo4j.areas.items():
        print(
            f"{area:<20}"
            f"{len(delta.added):>8}"
            f"{len(delta.updated):>10}"
            f"{len(delta.deleted):>10}"
        )

    print("\n" + "-" * 65)
    print(f"TOTAL CHANGES: {plan.total_changes}")
    print(f"TOTAL DELETIONS: {plan.total_deletions}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CASE-001 integrated data pipeline")

    parser.add_argument(
        "--root",
        type=Path,
        default=Path("../.local/case001_v7_1"),
        help="CASE-001 원본 데이터 폴더",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="변경사항을 실제 DB에 적용",
    )

    parser.add_argument(
        "--allow-delete",
        action="store_true",
        help="삭제 대상이 있는 경우 삭제 허용",
    )

    args = parser.parse_args()

    if args.allow_delete and not args.apply:
        parser.error("--allow-delete는 --apply와 함께 사용해야 합니다.")

    # 원본 검증이 실패하면 DB 연결 전에 중단
    sources = load_pipeline_sources(args.root)

    qdrant_client = QdrantClient(url=settings.qdrant_url)

    try:
        neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_user,
                settings.neo4j_password.get_secret_value(),
            ),
        )

        try:
            neo4j_driver.verify_connectivity()

            print("[PASS] CASE-001 source validation")
            print(f"[INFO] Qdrant chunks: {len(sources.records)}")

            plan = run_pipeline(
                sources,
                qdrant_client=qdrant_client,
                neo4j_driver=neo4j_driver,
                embedder=OllamaEmbedder(),
                apply=args.apply,
                allow_delete=args.allow_delete,
            )

            print_pipeline_plan(plan)

            if args.apply:
                print("\nAPPLY COMPLETED")
            else:
                print("\nDRY RUN ONLY - NO DATABASE CHANGES")

        finally:
            neo4j_driver.close()

    finally:
        qdrant_client.close()


if __name__ == "__main__":
    main()
