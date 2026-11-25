"""Issue #165 - isolated CASE-001 expanded knowledge graph."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from neo4j import GraphDatabase

from crimescene.settings import settings

VERSION = "case001_1120"
CASE_ID = "CASE-001"

NPC_IDS = frozenset(
    f"C{i:02d}" for i in range(1, 11)
)

EVIDENCE_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)


def digest(row):
    return hashlib.sha256(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def build_snapshot(catalog):
    if (
        catalog["case_id"] != CASE_ID
        or catalog["content_version"] != VERSION
        or catalog["runtime_enabled"] is not False
    ):
        raise ValueError("Invalid staging catalog")

    evidence = catalog["evidence"]
    relationships = catalog["relationships"]
    links = catalog["evidence_links"]

    if set(evidence) != EVIDENCE_IDS:
        raise ValueError("Expected 30 evidence IDs")

    if len(relationships) != 58 or len(links) != 23:
        raise ValueError("Unexpected relationship count")

    nodes = {}
    edges = {}

    def add_node(entity_id, entity_type):
        if (
            not isinstance(entity_id, str)
            or not entity_id.strip()
        ):
            raise ValueError("Invalid entity ID")

        row = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "case_id": CASE_ID,
            "content_version": VERSION,
            "runtime_enabled": False,
        }

        if entity_id in nodes and nodes[entity_id] != row:
            raise ValueError("Entity type collision")

        nodes[entity_id] = row

    def add_edge(
        edge_id,
        source_id,
        target_id,
        kind,
        relation,
        source_hash,
        **metadata,
    ):
        if edge_id in edges:
            raise ValueError("Duplicate edge ID")

        if source_id not in nodes or target_id not in nodes:
            raise ValueError("Unknown edge endpoint")

        if source_id == target_id:
            raise ValueError("Self-referencing edge")

        if not isinstance(relation, str) or not relation.strip():
            raise ValueError("Empty relationship")

        edges[edge_id] = {
            "edge_id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "kind": kind,
            "relation": relation,
            "case_id": CASE_ID,
            "content_version": VERSION,
            "source_sha256": source_hash,
            "contract_approved": False,
            "runtime_enabled": False,
            **metadata,
        }

    for npc_id in sorted(NPC_IDS):
        add_node(npc_id, "npc")

    for eid in sorted(EVIDENCE_IDS):
        add_node(eid, "evidence")

    for index, row in enumerate(
        relationships,
        start=1,
    ):
        source = row["from_id"]
        target = row["to_id"]

        if (
            row["from_type"] != "npc"
            or source not in NPC_IDS
        ):
            raise ValueError("Invalid relationship source")

        target_type = row["to_type"]

        if target_type == "npc":
            if target not in NPC_IDS:
                raise ValueError("Unknown NPC target")

        elif target_type == "evidence":
            if target not in EVIDENCE_IDS:
                raise ValueError("Unknown evidence target")

        elif target_type == "person":
            add_node(target, "person")

        else:
            raise ValueError("Unknown relationship type")

        stage = row["public_from_stage"]

        if stage not in {"S1", "S2", "S3"}:
            raise ValueError("Invalid disclosure stage")

        period = int(row["period"])

        if period not in (2016, 2026):
            raise ValueError("Invalid incident period")

        add_edge(
            f"REL-1120-{index:03d}",
            source,
            target,
            "npc_relationship",
            row["relationship"],
            digest(row),
            minimum_npc_stage=int(stage[1]),
            incident_year=period,
        )

    for index, row in enumerate(links, start=1):
        source = row["from_evidence"]
        target = row["to_evidence"]

        if not {source, target}.issubset(EVIDENCE_IDS):
            raise ValueError("Unknown evidence relationship")

        add_edge(
            f"LINK-1120-{index:03d}",
            source,
            target,
            "evidence_link",
            row["relationship"],
            digest(row),
            inference_id=row["resulting_inference"],
            presentation_mode=row["presentation_mode"],
        )

    for eid, item in sorted(evidence.items()):
        rule = item.get("legacy_rule", item)
        holder = rule["holder"]

        if holder not in NPC_IDS:
            raise ValueError("Unknown evidence holder")

        add_edge(
            f"HOLDER-1120-{eid}",
            holder,
            eid,
            "evidence_holder",
            "HOLDS_EVIDENCE",
            digest({
                "evidence_id": eid,
                "holder": holder,
            }),
        )

    if len(edges) != 111:
        raise ValueError("Unexpected graph edge count")

    return nodes, edges


def read_snapshot(tx):
    nodes = {}
    edges = {}

    records = tx.run("""
        MATCH (n:Case1120StagingEntity)
        RETURN properties(n) AS row
    """)

    for record in records:
        row = record["row"]
        key = row["entity_id"]

        if key in nodes:
            raise ValueError("Duplicate stored entity")

        nodes[key] = row

    records = tx.run("""
        MATCH (a)-[r]->(b)
        WHERE a:Case1120StagingEntity
           OR b:Case1120StagingEntity
           OR type(r) = 'CASE1120_STAGING_RELATION'
        RETURN
            properties(r) AS row,
            a.entity_id AS source,
            b.entity_id AS target,
            labels(a) AS source_labels,
            labels(b) AS target_labels,
            type(r) AS relation_type
    """)

    for record in records:
        row = record["row"]

        if (
            record["relation_type"]
            != "CASE1120_STAGING_RELATION"
            or record["source_labels"]
            != ["Case1120StagingEntity"]
            or record["target_labels"]
            != ["Case1120StagingEntity"]
            or record["source"] != row.get("source_id")
            or record["target"] != row.get("target_id")
        ):
            raise ValueError("Cross-version graph relationship")

        key = row["edge_id"]

        if key in edges:
            raise ValueError("Duplicate stored relationship")

        edges[key] = row

    return nodes, edges


def legacy_counts(tx):
    node_count = tx.run("""
        MATCH (n)
        WHERE NOT n:Case1120StagingEntity
        RETURN count(n) AS total
    """).single()["total"]

    edge_count = tx.run("""
        MATCH ()-[r]->()
        WHERE type(r) <> 'CASE1120_STAGING_RELATION'
        RETURN count(r) AS total
    """).single()["total"]

    return node_count, edge_count


def apply_snapshot(tx, nodes, edges):
    before = legacy_counts(tx)
    current_nodes, current_edges = read_snapshot(tx)

    if current_nodes or current_edges:
        if (
            current_nodes != nodes
            or current_edges != edges
        ):
            raise ValueError("Existing staging snapshot mismatch")

        return before, before, False

    tx.run("""
        UNWIND $rows AS row
        CREATE (n:Case1120StagingEntity)
        SET n = row
    """, rows=list(nodes.values())).consume()

    tx.run("""
        UNWIND $rows AS row

        MATCH (a:Case1120StagingEntity {
            entity_id: row.source_id,
            case_id: row.case_id,
            content_version: row.content_version
        })

        MATCH (b:Case1120StagingEntity {
            entity_id: row.target_id,
            case_id: row.case_id,
            content_version: row.content_version
        })

        CREATE (a)-[r:CASE1120_STAGING_RELATION]->(b)
        SET r = row
    """, rows=list(edges.values())).consume()

    if read_snapshot(tx) != (nodes, edges):
        raise ValueError("Graph verification failed")

    after = legacy_counts(tx)

    if after != before:
        raise ValueError("Legacy graph changed")

    return before, after, True


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")

    args = parser.parse_args()

    catalog = json.loads(
        args.catalog.read_text(encoding="utf-8-sig")
    )

    nodes, edges = build_snapshot(catalog)

    print("EXPECTED NODES:", len(nodes))
    print("EXPECTED RELATIONSHIPS:", len(edges))

    print("NODE TYPES:", dict(Counter(
        row["entity_type"]
        for row in nodes.values()
    )))

    print("EDGE TYPES:", dict(Counter(
        row["kind"]
        for row in edges.values()
    )))

    uri = settings.neo4j_uri
    host = urlsplit(uri).hostname

    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Local Neo4j required")

    if settings.app_env.lower() != "development":
        raise ValueError("Development environment required")

    with GraphDatabase.driver(
        uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
    ) as driver:
        driver.verify_connectivity()

        with driver.session() as session:
            current = session.execute_read(read_snapshot)
            legacy = session.execute_read(legacy_counts)

            print("LEGACY NODES BEFORE:", legacy[0])
            print("LEGACY RELATIONSHIPS BEFORE:", legacy[1])
            print("EXISTING STAGING NODES:", len(current[0]))
            print("EXISTING STAGING EDGES:", len(current[1]))

            if any(current) and current != (nodes, edges):
                raise ValueError("Staging snapshot mismatch")

            if not args.apply:
                print("DRY RUN ONLY - NO DATABASE CHANGES")
                return

            before, after, created = session.execute_write(
                apply_snapshot,
                nodes,
                edges,
            )

            actual = session.execute_read(read_snapshot)

            if actual != (nodes, edges):
                raise ValueError("Post-commit verification failed")

            print("CREATED:", created)
            print("STAGING NODES:", len(actual[0]))
            print("STAGING RELATIONSHIPS:", len(actual[1]))
            print("LEGACY NODES AFTER:", after[0])
            print("LEGACY RELATIONSHIPS AFTER:", after[1])
            print("LEGACY UNCHANGED:", before == after)
            print("NEO4J STAGING INGEST COMPLETE")


if __name__ == "__main__":
    main()
