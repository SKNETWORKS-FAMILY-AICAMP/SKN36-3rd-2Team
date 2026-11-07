"""CASE-001 통합 데이터 적재 파이프라인 테스트."""

from unittest.mock import Mock

import pytest

import crimescene.db.data_pipeline as pipeline
from crimescene.db.data_pipeline import (
    PipelinePlan,
    PipelineSources,
    run_pipeline,
)
from crimescene.db.neo4j_sync import (
    AREAS,
    Neo4jSyncPlan,
    SyncDelta,
)
from crimescene.db.qdrant_sync import QdrantSyncPlan


@pytest.fixture(autouse=True)
def development_environment(monkeypatch):
    """실제 .env 설정과 무관하게 개발 환경으로 테스트한다."""

    monkeypatch.setattr(
        pipeline.settings,
        "app_env",
        "development",
    )


@pytest.fixture
def sources():
    """DB 적재 자체를 Mock 처리하기 위한 테스트 원본."""

    return PipelineSources(
        records=(),
        document_ids=frozenset(),
        npc_card_ids=frozenset(),
        policy_ids=frozenset(),
        graph_snapshot={area: {} for area in AREAS},
    )


def make_plan(
    *,
    q_added=(),
    q_deleted=(),
    graph_added=(),
    graph_deleted=(),
):
    """테스트용 변경 계획 생성."""

    qdrant = QdrantSyncPlan(
        added=tuple(q_added),
        updated=(),
        unchanged=(),
        deleted=tuple(q_deleted),
    )

    areas = {
        area: SyncDelta(
            added=(),
            updated=(),
            deleted=(),
            unchanged=(),
        )
        for area in AREAS
    }

    areas["entities"] = SyncDelta(
        added=tuple(graph_added),
        updated=(),
        deleted=tuple(graph_deleted),
        unchanged=(),
    )

    return PipelinePlan(
        qdrant=qdrant,
        neo4j=Neo4jSyncPlan(areas=areas),
    )


def execute(sources, **kwargs):
    """테스트용 통합 파이프라인 호출."""

    return run_pipeline(
        sources,
        qdrant_client=Mock(),
        neo4j_driver=Mock(),
        embedder=Mock(),
        **kwargs,
    )


def test_dry_run_never_writes(monkeypatch, sources):
    """Dry Run에서는 두 DB 모두 변경하지 않는다."""

    plan = make_plan(
        q_added=("point-1",),
        graph_added=("C01",),
    )

    inspect = Mock(return_value=plan)
    qdrant_apply = Mock()
    neo4j_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        inspect,
    )

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        qdrant_apply,
    )

    monkeypatch.setattr(
        pipeline,
        "apply_neo4j_snapshot",
        neo4j_apply,
    )

    result = execute(sources)

    assert result.total_changes == 2
    assert inspect.call_count == 1

    qdrant_apply.assert_not_called()
    neo4j_apply.assert_not_called()


def test_apply_both_databases(monkeypatch, sources):
    """두 DB의 변경사항을 순서대로 적용한다."""

    before = make_plan(
        q_added=("point-1",),
        graph_added=("C01",),
    )

    after = make_plan()

    inspect = Mock(side_effect=[before, after])
    qdrant_apply = Mock()
    neo4j_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        inspect,
    )

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        qdrant_apply,
    )

    monkeypatch.setattr(
        pipeline,
        "apply_neo4j_snapshot",
        neo4j_apply,
    )

    result = execute(
        sources,
        apply=True,
    )

    assert result.total_changes == 2
    assert inspect.call_count == 2

    qdrant_apply.assert_called_once()
    neo4j_apply.assert_called_once()

    assert qdrant_apply.call_args.kwargs["dry_run"] is False
    assert qdrant_apply.call_args.kwargs["allow_delete"] is False


def test_no_changes_skip_apply(monkeypatch, sources):
    """이미 동기화된 DB에는 쓰기 작업을 하지 않는다."""

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        Mock(return_value=make_plan()),
    )

    qdrant_apply = Mock()
    neo4j_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        qdrant_apply,
    )

    monkeypatch.setattr(
        pipeline,
        "apply_neo4j_snapshot",
        neo4j_apply,
    )

    result = execute(
        sources,
        apply=True,
    )

    assert result.total_changes == 0

    qdrant_apply.assert_not_called()
    neo4j_apply.assert_not_called()


def test_deletion_requires_approval(monkeypatch, sources):
    """어느 한 DB에서라도 삭제가 필요하면 승인받는다."""

    plan = make_plan(
        q_added=("point-1",),
        graph_deleted=("C02",),
    )

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        Mock(return_value=plan),
    )

    qdrant_apply = Mock()
    neo4j_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        qdrant_apply,
    )

    monkeypatch.setattr(
        pipeline,
        "apply_neo4j_snapshot",
        neo4j_apply,
    )

    with pytest.raises(ValueError, match="allow-delete"):
        execute(
            sources,
            apply=True,
            allow_delete=False,
        )

    # 삭제 승인 실패 시 새 데이터 추가도 시작하지 않음
    qdrant_apply.assert_not_called()
    neo4j_apply.assert_not_called()


def test_production_apply_rejected(monkeypatch, sources):
    """관리자 원본을 포함한 통합 적재는 개발 환경만 허용한다."""

    monkeypatch.setattr(
        pipeline.settings,
        "app_env",
        "production",
    )

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        Mock(return_value=make_plan(q_added=("point-1",))),
    )

    qdrant_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        qdrant_apply,
    )

    with pytest.raises(RuntimeError, match="개발 환경"):
        execute(
            sources,
            apply=True,
        )

    qdrant_apply.assert_not_called()


def test_final_integrity_mismatch_rejected(
    monkeypatch,
    sources,
):
    """적재 후 변경사항이 남아 있으면 실패 처리한다."""

    changed = make_plan(q_added=("point-1",))

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        Mock(side_effect=[changed, changed]),
    )

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        Mock(),
    )

    with pytest.raises(RuntimeError, match="불일치"):
        execute(
            sources,
            apply=True,
        )


def test_embedding_failure_stops_graph_apply(
    monkeypatch,
    sources,
):
    """Qdrant 적재 실패 시 Neo4j 적용을 시작하지 않는다."""

    before = make_plan(
        q_added=("point-1",),
        graph_added=("C01",),
    )

    monkeypatch.setattr(
        pipeline,
        "inspect_pipeline",
        Mock(return_value=before),
    )

    monkeypatch.setattr(
        pipeline,
        "sync_qdrant_records",
        Mock(side_effect=RuntimeError("Embedding failed")),
    )

    neo4j_apply = Mock()

    monkeypatch.setattr(
        pipeline,
        "apply_neo4j_snapshot",
        neo4j_apply,
    )

    with pytest.raises(RuntimeError, match="Embedding failed"):
        execute(
            sources,
            apply=True,
        )

    neo4j_apply.assert_not_called()


def test_missing_source_directory_rejected(tmp_path):
    """원본 폴더가 없으면 DB 작업 이전에 중단한다."""

    missing_dir = tmp_path / "missing-case001"

    with pytest.raises(FileNotFoundError):
        pipeline.load_pipeline_sources(missing_dir)
