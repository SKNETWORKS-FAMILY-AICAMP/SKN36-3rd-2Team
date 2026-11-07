"""Neo4j 동기화 Apply 기능 테스트."""

from unittest.mock import MagicMock

import pytest

import crimescene.db.neo4j_sync_apply as sync_module
from crimescene.db.neo4j_sync import AREAS


def make_snapshot():
    return {area: {} for area in AREAS}


def test_no_changes_skip_writes(monkeypatch):
    """변경사항이 없으면 쓰기를 실행하지 않는다."""

    snapshot = make_snapshot()

    monkeypatch.setattr(
        sync_module,
        "_read_snapshot_tx",
        lambda tx: snapshot,
    )

    tx = MagicMock()

    plan = sync_module._sync_transaction(
        tx,
        snapshot,
        False,
    )

    assert plan.total_changes == 0
    tx.run.assert_not_called()


def test_deletion_requires_approval(monkeypatch):
    """삭제가 필요한 경우 승인 없이 적용하지 않는다."""

    expected = make_snapshot()
    actual = make_snapshot()

    actual["entities"]["C01"] = {
        "case_id": "CASE-001",
        "entity_id": "C01",
        "entity_type": "Person",
        "label": "윤태식",
    }

    monkeypatch.setattr(
        sync_module,
        "_read_snapshot_tx",
        lambda tx: actual,
    )

    tx = MagicMock()

    with pytest.raises(ValueError, match="allow-delete"):
        sync_module._sync_transaction(
            tx,
            expected,
            False,
        )

    tx.run.assert_not_called()


def test_entity_type_change_rejected(monkeypatch):
    """엔티티 유형 변경은 자동으로 적용하지 않는다."""

    expected = make_snapshot()
    actual = make_snapshot()

    expected["entities"]["C01"] = {
        "case_id": "CASE-001",
        "entity_id": "C01",
        "entity_type": "Place",
        "label": "테스트 장소",
    }

    actual["entities"]["C01"] = {
        "case_id": "CASE-001",
        "entity_id": "C01",
        "entity_type": "Person",
        "label": "윤태식",
    }

    monkeypatch.setattr(
        sync_module,
        "_read_snapshot_tx",
        lambda tx: actual,
    )

    tx = MagicMock()

    with pytest.raises(ValueError, match="수동 마이그레이션"):
        sync_module._sync_transaction(
            tx,
            expected,
            False,
        )

    tx.run.assert_not_called()


def test_new_entity_applied_and_verified(monkeypatch):
    """신규 엔티티를 적재한 후 무결성을 검증한다."""

    expected = make_snapshot()
    actual = make_snapshot()

    expected["entities"]["C01"] = {
        "case_id": "CASE-001",
        "entity_id": "C01",
        "entity_type": "Person",
        "label": "윤태식",
    }

    snapshots = iter([actual, expected])

    monkeypatch.setattr(
        sync_module,
        "_read_snapshot_tx",
        lambda tx: next(snapshots),
    )

    tx = MagicMock()

    plan = sync_module._sync_transaction(
        tx,
        expected,
        False,
    )

    assert plan.areas["entities"].added == ("C01",)
    assert plan.total_changes == 1
    assert tx.run.called


def test_verification_failure_rejected(monkeypatch):
    """적재 후 불일치가 남으면 오류를 발생시킨다."""

    expected = make_snapshot()
    actual = make_snapshot()

    expected["entities"]["C01"] = {
        "case_id": "CASE-001",
        "entity_id": "C01",
        "entity_type": "Person",
        "label": "윤태식",
    }

    monkeypatch.setattr(
        sync_module,
        "_read_snapshot_tx",
        lambda tx: actual,
    )

    tx = MagicMock()

    with pytest.raises(RuntimeError, match="불일치"):
        sync_module._sync_transaction(
            tx,
            expected,
            False,
        )
