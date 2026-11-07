"""독립 테스트 컨테이너에서 Neo4j 동기화 검증."""

import os
from copy import deepcopy
from time import sleep

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

from crimescene.db.neo4j_event_ingest import ensure_admin_schema
from crimescene.db.neo4j_schema import ensure_graph_schema
from crimescene.db.neo4j_sync import (
    AREAS,
    build_sync_plan,
    read_database_snapshot,
)
from crimescene.db.neo4j_sync_apply import apply_neo4j_snapshot

TEST_URI = "bolt://127.0.0.1:7688"
CASE_ID = "CASE-001"


def make_snapshot():
    """가상 테스트 데이터를 사용한 그래프 스냅샷."""

    snapshot = {area: {} for area in AREAS}

    snapshot["entities"] = {
        "C01": {
            "case_id": CASE_ID,
            "entity_id": "C01",
            "entity_type": "Person",
            "label": "테스트 인물 A",
        },
        "C02": {
            "case_id": CASE_ID,
            "entity_id": "C02",
            "entity_type": "Person",
            "label": "테스트 인물 B",
        },
        "E01": {
            "case_id": CASE_ID,
            "entity_id": "E01",
            "entity_type": "Evidence",
            "label": "E01",
        },
    }

    snapshot["relationships"] = {
        "REL-001": {
            "case_id": CASE_ID,
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "C02",
            "relation": "KNOWS",
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
        }
    }

    snapshot["evidence_holders"] = {
        "E01": {
            "evidence_id": "E01",
            "holder_id": "C01",
            "access_scope": "collected_evidence",
            "source": "evidence_rules.holder",
        }
    }

    snapshot["admin_events"] = {
        "EVT-001": {
            "case_id": CASE_ID,
            "event_id": "EVT-001",
            "description": "테스트 사건 발생",
            "incident_year": 2026,
            "truth_status": "admin_canonical",
            "access_scope": "admin_only",
        }
    }

    snapshot["admin_entities"] = {
        "C01": {
            "entity_type": "Person",
        }
    }

    snapshot["admin_mentions"] = {
        "EVT-001::C01": {},
    }

    return snapshot


@pytest.fixture(scope="module")
def test_driver():
    """오직 7688번 테스트 서버에만 연결한다."""

    requested_uri = os.environ.get("CRIMESCENE_TEST_NEO4J_URI")

    password = os.environ.get("CRIMESCENE_TEST_NEO4J_PASSWORD")

    if requested_uri != TEST_URI or not password:
        pytest.skip("별도 Neo4j 테스트 서버 환경변수가 설정되지 않았습니다.")

    driver = GraphDatabase.driver(
        TEST_URI,
        auth=("neo4j", password),
    )

    try:
        # 테스트 컨테이너 부팅 확인
        for attempt in range(30):
            try:
                driver.verify_connectivity()
                break
            except (ServiceUnavailable, SessionExpired, OSError):
                if attempt == 29:
                    pytest.fail("테스트 Neo4j 서버에 연결할 수 없습니다.")
                sleep(1)

        # 비어 있는 테스트 DB인지 먼저 검증합니다.
        # 기존 데이터가 있다면 삭제하지 않고 중단합니다.
        with driver.session() as session:
            count = session.run("MATCH (n) RETURN count(n) AS total").single()["total"]

        if count != 0:
            pytest.fail(
                "테스트 DB에 기존 데이터가 있습니다. 안전을 위해 테스트를 중단합니다."
            )

        ensure_graph_schema(driver)
        ensure_admin_schema(driver)

        yield driver

    finally:
        driver.close()


@pytest.fixture
def clean_graph(test_driver):
    """각 테스트의 데이터는 독립 컨테이너에서 초기화한다."""

    with test_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n").consume()

    yield test_driver

    with test_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n").consume()


def assert_matches(driver, expected):
    """DB가 기대 상태와 일치하는지 확인한다."""

    actual = read_database_snapshot(driver)

    plan = build_sync_plan(expected, actual)

    assert plan.total_changes == 0

    return actual


def test_initial_and_repeated_ingest(clean_graph):
    """최초 적재와 반복 적재의 중복 방지를 검증한다."""

    driver = clean_graph
    expected = make_snapshot()

    first = apply_neo4j_snapshot(
        driver,
        expected,
    )

    assert first.total_changes == 8

    assert_matches(driver, expected)

    second = apply_neo4j_snapshot(
        driver,
        expected,
    )

    assert second.total_changes == 0

    actual = assert_matches(driver, expected)

    assert len(actual["entities"]) == 3
    assert len(actual["relationships"]) == 1
    assert len(actual["evidence_holders"]) == 1
    assert len(actual["admin_events"]) == 1
    assert len(actual["admin_entities"]) == 1
    assert len(actual["admin_mentions"]) == 1


def test_updated_relationship_and_holder(clean_graph):
    """인물 관계와 증거 보유자 변경을 검증한다."""

    driver = clean_graph
    original = make_snapshot()

    apply_neo4j_snapshot(driver, original)

    updated = deepcopy(original)

    updated["entities"]["C02"]["label"] = "수정된 테스트 인물 B"

    updated["entities"]["C03"] = {
        "case_id": CASE_ID,
        "entity_id": "C03",
        "entity_type": "Person",
        "label": "신규 테스트 인물 C",
    }

    updated["relationships"]["REL-001"]["target_id"] = "C03"

    updated["evidence_holders"]["E01"]["holder_id"] = "C02"

    updated["admin_events"]["EVT-001"]["description"] = "수정된 테스트 사건"

    plan = apply_neo4j_snapshot(
        driver,
        updated,
    )

    assert plan.areas["entities"].added == ("C03",)
    assert plan.areas["entities"].updated == ("C02",)
    assert plan.areas["relationships"].updated == ("REL-001",)
    assert plan.areas["evidence_holders"].updated == ("E01",)
    assert plan.areas["admin_events"].updated == ("EVT-001",)

    assert_matches(driver, updated)

    repeated = apply_neo4j_snapshot(
        driver,
        updated,
    )

    assert repeated.total_changes == 0


def test_admin_mention_change(clean_graph):
    """관리자 사건 참조 인물 변경을 검증한다."""

    driver = clean_graph
    original = make_snapshot()

    apply_neo4j_snapshot(driver, original)

    updated = deepcopy(original)

    updated["admin_entities"] = {
        "C02": {
            "entity_type": "Person",
        }
    }

    updated["admin_mentions"] = {
        "EVT-001::C02": {},
    }

    plan = apply_neo4j_snapshot(
        driver,
        updated,
        allow_delete=True,
    )

    assert plan.areas["admin_entities"].added == ("C02",)
    assert plan.areas["admin_entities"].deleted == ("C01",)

    assert_matches(driver, updated)


def test_delete_requires_approval(clean_graph):
    """삭제 승인 전에는 데이터를 변경하지 않는다."""

    driver = clean_graph
    original = make_snapshot()

    apply_neo4j_snapshot(driver, original)

    updated = deepcopy(original)

    del updated["entities"]["C02"]
    updated["relationships"].clear()

    with pytest.raises(ValueError, match="allow-delete"):
        apply_neo4j_snapshot(
            driver,
            updated,
            allow_delete=False,
        )

    # 삭제가 거부되면 원래 데이터가 유지됩니다.
    assert_matches(driver, original)

    plan = apply_neo4j_snapshot(
        driver,
        updated,
        allow_delete=True,
    )

    assert plan.areas["entities"].deleted == ("C02",)
    assert plan.areas["relationships"].deleted == ("REL-001",)

    assert_matches(driver, updated)


def test_missing_reference_rolls_back(clean_graph):
    """연결 대상이 없으면 전체 적재를 롤백한다."""

    driver = clean_graph
    original = make_snapshot()

    apply_neo4j_snapshot(driver, original)

    invalid = deepcopy(original)

    # 신규 노드 생성 이후 관계 적재가 실패하도록 구성
    invalid["entities"]["C03"] = {
        "case_id": CASE_ID,
        "entity_id": "C03",
        "entity_type": "Person",
        "label": "롤백 테스트 인물",
    }

    invalid["relationships"]["REL-002"] = {
        **invalid["relationships"]["REL-001"],
        "edge_id": "REL-002",
        "target_id": "C99",
    }

    with pytest.raises(RuntimeError, match="불일치"):
        apply_neo4j_snapshot(
            driver,
            invalid,
        )

    # 신규 노드 C03도 롤백되어야 합니다.
    assert_matches(driver, original)


def test_unexpected_relationship_prevents_delete(clean_graph):
    """예상하지 못한 연결이 남아 있으면 삭제를 중단한다."""

    driver = clean_graph
    original = make_snapshot()

    apply_neo4j_snapshot(driver, original)

    # 기존 CASE_RELATION 외에 예상하지 못한 관계 생성
    with driver.session() as session:
        session.run(
            """
            MATCH (a:CaseEntity {
                case_id: $case_id,
                entity_id: 'C02'
            })
            MATCH (b:CaseEntity {
                case_id: $case_id,
                entity_id: 'C01'
            })
            CREATE (a)-[:EXTRA_TEST_LINK]->(b)
            """,
            case_id=CASE_ID,
        ).consume()

    updated = deepcopy(original)

    del updated["entities"]["C02"]
    updated["relationships"].clear()

    with pytest.raises(Neo4jError):
        apply_neo4j_snapshot(
            driver,
            updated,
            allow_delete=True,
        )

    # 이전에 삭제하려 했던 CASE_RELATION도 롤백됩니다.
    assert_matches(driver, original)

    with driver.session() as session:
        count = session.run(
            """
            MATCH ()-[r:EXTRA_TEST_LINK]->()
            RETURN count(r) AS total
            """
        ).single()["total"]

    assert count == 1
