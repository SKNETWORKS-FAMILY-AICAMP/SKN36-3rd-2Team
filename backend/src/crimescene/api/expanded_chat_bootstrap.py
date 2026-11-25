
"""Issue #165 - expanded staging RAG runtime."""

import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from neo4j import GraphDatabase
from ollama import Client
from qdrant_client import QdrantClient

from crimescene.chat.expanded_personas import build_expanded_personas
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.db.expanded_neo4j_ingest import (
    build_snapshot,
    read_snapshot,
)
from crimescene.db.qdrant_sync import sync_qdrant_records
from crimescene.ingest.expanded_dataset import (
    COLLECTION,
    load_verified_dataset,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.retriever.versioned_retrieval import validate_catalog_version
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.settings import settings

VERSION = "case001_1120"


def build_staging_evidence_rules(catalog):
    if (
        catalog["case_id"] != "CASE-001"
        or catalog["content_version"] != VERSION
        or catalog["runtime_enabled"] is not False
    ):
        raise ValueError("Invalid staging catalog")

    rules = {}

    for eid, item in catalog["evidence"].items():
        if "legacy_rule" in item:
            rules[eid] = EvidenceRule.model_validate(
                item["legacy_rule"]
            )
        else:
            rules[eid] = EvidenceRule(
                name=item["name"],
                score=item["proposed_score"],
                holder=item["holder"],
                prerequisites=[],
                presentation=[],
                q=[],
            )

    validate_catalog_version(VERSION, rules)

    return rules


@contextmanager
def load_expanded_staging_resources(
    *,
    catalog_path: Path,
    dataset_root: Path,
    collection_name: str = COLLECTION,
):
    """Load verified local resources without publishing them."""

    if settings.app_env.lower() != "development":
        raise PermissionError("Development runtime required")

    if urlsplit(settings.neo4j_uri).hostname not in {
        "localhost", "127.0.0.1", "::1"
    }:
        raise PermissionError("Local Neo4j required")

    catalog = json.loads(
        catalog_path.read_text(encoding="utf-8-sig")
    )

    rules = build_staging_evidence_rules(catalog)

    records, docs, cards, policies = load_verified_dataset(
        dataset_root,
        expected_collection=collection_name,
    )

    nodes, edges = build_snapshot(catalog)

    with ExitStack() as stack:
        qdrant = QdrantClient(
            url="http://127.0.0.1:6333",
            timeout=120,
        )
        stack.callback(qdrant.close)

        neo4j = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_user,
                settings.neo4j_password.get_secret_value(),
            ),
        )

        stack.callback(neo4j.close)
        neo4j.verify_connectivity()

        ollama = Client(
            host="http://127.0.0.1:11434",
            timeout=120,
        )

        ollama.show("bge-m3")

        embedder = OllamaEmbedder(
            model="bge-m3",
            vector_size=1024,
            client=ollama,
        )

        # Verify vector payloads against trusted source records.
        plan = sync_qdrant_records(
            records,
            client=qdrant,
            embedder=embedder,
            document_ids={doc.doc_id for doc in docs},
            npc_card_ids={card["id"] for card in cards},
            valid_policy_ids=set(policies),
            collection_name=collection_name,
            dry_run=True,
        )

        if plan.total_changes:
            raise ValueError("Qdrant snapshot mismatch")

        if qdrant.count(
            collection_name=collection_name,
            exact=True,
        ).count != len(records):
            raise ValueError("Unexpected Qdrant points")

        # Verify graph integrity without modifying the database.
        with neo4j.session() as session:
            actual = session.execute_read(read_snapshot)

        if actual != (nodes, edges):
            raise ValueError("Neo4j snapshot mismatch")

        resources = NPCRAGResources(
            personas=build_expanded_personas(),
            qdrant_client=qdrant,
            neo4j_driver=neo4j,
            embedder=embedder,
            encoder=KoreanBM25Encoder(),
            trusted_records=tuple(records),
            documents=tuple(docs),
            npc_cards=tuple(cards),
            registry=tuple(
                {
                    "entity_id": eid,
                    "case_id": "CASE-001",
                    "label": eid,
                    "type": {
                        "npc": "Person",
                        "person": "Person",
                        "evidence": "Evidence",
                    }[row["entity_type"]],
                }
                for eid, row in sorted(nodes.items())
            ),
            trusted_edges=(),
            evidence_rules=rules,
            evaluator=PolicyEvaluator(policies),
            content_version=VERSION,
            collection_name=collection_name,
        )

        print("RAG COLLECTION:", collection_name)
        print("RUNTIME VERSION:", VERSION)
        print("EVIDENCE RULES:", len(rules))
        print("RAG RECORDS:", len(records))
        print("GRAPH NODES:", len(nodes))
        print("GRAPH EDGES:", len(edges))
        print("PUBLISHED GRAPH EDGES: 0")
        print("STAGING RUNTIME READY")

        yield resources
