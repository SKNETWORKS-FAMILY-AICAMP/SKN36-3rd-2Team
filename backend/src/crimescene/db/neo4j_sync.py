"""CASE-001 Neo4j 동기화 계획 생성 및 Dry Run."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from neo4j import GraphDatabase

from crimescene.db.ingest_integrity import validate_neo4j_records
from crimescene.db.neo4j_event_ingest import build_admin_graph_rows
from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.loaders.relationship_loader import load_relationship_edges
from crimescene.scenario.source_timeline import load_source_timeline
from crimescene.settings import settings

CASE_ID = "CASE-001"

AREAS = (
    "entities",
    "relationships",
    "evidence_holders",
    "admin_events",
    "admin_entities",
    "admin_mentions",
)


@dataclass(frozen=True)
class SyncDelta:
    """데이터 영역별 변경사항."""

    added: tuple[str, ...]
    updated: tuple[str, ...]
    deleted: tuple[str, ...]
    unchanged: tuple[str, ...]

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.updated) + len(self.deleted)


@dataclass(frozen=True)
class Neo4jSyncPlan:
    """전체 그래프 동기화 계획."""

    areas: dict[str, SyncDelta]

    @property
    def total_changes(self) -> int:
        return sum(delta.total_changes for delta in self.areas.values())


def _normalize(value):
    """Neo4j 날짜 등 DB 자료형을 비교 가능한 값으로 변환."""

    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_normalize(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def compare_records(
    expected: dict[str, dict],
    actual: dict[str, dict],
) -> SyncDelta:
    """원본과 DB 상태를 비교한다."""

    expected_ids = set(expected)
    actual_ids = set(actual)

    added = sorted(expected_ids - actual_ids)
    deleted = sorted(actual_ids - expected_ids)

    updated = []
    unchanged = []

    for record_id in sorted(expected_ids & actual_ids):
        expected_data = expected[record_id]
        actual_data = actual[record_id]

        # 원본에서 관리하는 필드만 비교한다.
        changed = any(
            _normalize(actual_data.get(field)) != _normalize(value)
            for field, value in expected_data.items()
        )

        if changed:
            updated.append(record_id)
        else:
            unchanged.append(record_id)

    return SyncDelta(
        added=tuple(added),
        updated=tuple(updated),
        deleted=tuple(deleted),
        unchanged=tuple(unchanged),
    )


def build_expected_snapshot(
    entities,
    relationships,
    evidence_rules,
    events,
) -> dict[str, dict[str, dict]]:
    """검증된 원본을 Neo4j의 기대 상태로 변환한다."""

    validate_neo4j_records(
        entities=entities,
        relationships=relationships,
        evidence_rules=evidence_rules,
        events=events,
    )

    snapshot = {area: {} for area in AREAS}

    # 1. 원본 엔티티
    for entity in entities:
        snapshot["entities"][entity["entity_id"]] = {
            "case_id": CASE_ID,
            "entity_id": entity["entity_id"],
            "entity_type": entity["type"],
            "label": entity["label"],
        }

    # 2. 증거 노드 E01~E10
    for evidence_id in evidence_rules:
        if evidence_id not in snapshot["entities"]:
            snapshot["entities"][evidence_id] = {
                "case_id": CASE_ID,
                "entity_id": evidence_id,
                "entity_type": "Evidence",
                "label": evidence_id,
            }

    # 3. 기존 인물·사건 관계
    for edge in relationships:
        snapshot["relationships"][edge.edge_id] = edge.model_dump(mode="json")

    # 4. 증거 보유자 관계
    for evidence_id, rule in evidence_rules.items():
        snapshot["evidence_holders"][evidence_id] = {
            "evidence_id": evidence_id,
            "holder_id": rule.holder.strip(),
            "access_scope": "collected_evidence",
            "source": "evidence_rules.holder",
        }

    # 5. 관리자 사건 및 인물 참조
    event_rows, mention_rows = build_admin_graph_rows(
        events,
        entities,
    )

    for row in event_rows:
        snapshot["admin_events"][row["event_id"]] = {
            **row,
            "access_scope": "admin_only",
        }

    entity_types = {entity["entity_id"]: entity["type"] for entity in entities}

    for row in mention_rows:
        entity_id = row["entity_id"]
        event_id = row["event_id"]

        snapshot["admin_entities"][entity_id] = {
            "entity_type": entity_types[entity_id],
        }

        mention_key = f"{event_id}::{entity_id}"

        snapshot["admin_mentions"][mention_key] = {}

    return snapshot


QUERIES = {
    "entities": """
        MATCH (n:CaseEntity {case_id: $case_id})
        RETURN n.entity_id AS key,
               properties(n) AS props
    """,
    "relationships": """
        MATCH (s:CaseEntity)-[r:CASE_RELATION {
            case_id: $case_id
        }]->(t:CaseEntity)
        RETURN r.edge_id AS key,
               properties(r) AS props,
               s.entity_id AS source_id,
               t.entity_id AS target_id
    """,
    "evidence_holders": """
        MATCH (e:CaseEntity)-[r:EVIDENCE_HOLDER {
            case_id: $case_id
        }]->(h:CaseEntity)
        RETURN r.evidence_id AS key,
               {
                   evidence_id: e.entity_id,
                   holder_id: h.entity_id,
                   access_scope: r.access_scope,
                   source: r.source
               } AS props
    """,
    "admin_events": """
        MATCH (e:AdminEvent {case_id: $case_id})
        RETURN e.event_id AS key,
               properties(e) AS props
    """,
    "admin_entities": """
        MATCH (n:AdminEntity {case_id: $case_id})
        RETURN n.entity_id AS key,
               {entity_type: n.entity_type} AS props
    """,
    "admin_mentions": """
        MATCH (e:AdminEvent {case_id: $case_id})
              -[:ADMIN_MENTIONS]->
              (n:AdminEntity {case_id: $case_id})
        RETURN e.event_id + '::' + n.entity_id AS key,
               {} AS props
    """,
}


def read_database_snapshot(driver):
    """Neo4j의 현재 상태를 읽기 전용으로 조회한다."""

    snapshot = {area: {} for area in AREAS}

    with driver.session() as session:
        for area, query in QUERIES.items():
            rows = session.run(
                query,
                case_id=CASE_ID,
            ).data()

            for row in rows:
                key = row["key"]

                if not isinstance(key, str) or not key:
                    raise ValueError(f"Neo4j 식별자 오류: {area}")

                if key in snapshot[area]:
                    raise ValueError(f"Neo4j 중복 식별자: {area}/{key}")

                props = dict(row["props"] or {})

                # 실제 그래프의 연결 방향 및 대상을 검증한다.
                if area == "relationships":
                    props["source_id"] = row["source_id"]
                    props["target_id"] = row["target_id"]

                snapshot[area][key] = props

    return snapshot


def build_sync_plan(expected, actual) -> Neo4jSyncPlan:
    """6개 데이터 영역의 변경 계획을 생성한다."""

    areas = {
        area: compare_records(
            expected[area],
            actual[area],
        )
        for area in AREAS
    }

    return Neo4jSyncPlan(areas=areas)


def find_source(root: Path, filename: str) -> Path:
    """원본 데이터 파일을 하위 폴더에서 검색한다."""

    matches = sorted(root.rglob(filename))

    if len(matches) != 1:
        raise RuntimeError(f"Expected one {filename}, found {len(matches)}: {matches}")

    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="CASE-001 Neo4j sync dry run")

    parser.add_argument(
        "--root",
        type=Path,
        default=Path("../.local/case001_v7_1"),
    )

    args = parser.parse_args()

    root = args.root.resolve()

    if not root.is_dir():
        raise FileNotFoundError(root)

    entities = load_entity_registry(find_source(root, "entity_registry.json"))

    relationships = load_relationship_edges(
        find_source(root, "relationship_edges_source.json")
    )

    evidence_rules = load_evidence_rules(find_source(root, "evidence_rules.json"))

    events = load_source_timeline(find_source(root, "timeline_events.json"))

    expected = build_expected_snapshot(
        entities,
        relationships,
        evidence_rules,
        events,
    )

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        ),
    )

    try:
        driver.verify_connectivity()

        actual = read_database_snapshot(driver)

    finally:
        driver.close()

    plan = build_sync_plan(expected, actual)

    print("=" * 65)
    print("CASE-001 NEO4J SYNC DRY RUN")
    print("=" * 65)

    print(
        f"{'AREA':<20}{'EXPECTED':>9}{'ACTUAL':>9}{'ADD':>6}{'UPDATE':>8}{'DELETE':>8}"
    )

    for area in AREAS:
        delta = plan.areas[area]

        print(
            f"{area:<20}"
            f"{len(expected[area]):>9}"
            f"{len(actual[area]):>9}"
            f"{len(delta.added):>6}"
            f"{len(delta.updated):>8}"
            f"{len(delta.deleted):>8}"
        )

    print("-" * 65)
    print(f"TOTAL CHANGES: {plan.total_changes}")
    print("DRY RUN ONLY: NO DATABASE CHANGES")


if __name__ == "__main__":
    main()
