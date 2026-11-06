from uuid import UUID, uuid5

import pytest

from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.hybrid_chunker import (
    build_hybrid_chunks,
)

POINT_ID_1 = UUID("550e8400-e29b-41d4-a716-446655440000")
POINT_ID_2 = UUID("550e8400-e29b-41d4-a716-446655440001")


def make_source(
    *,
    source_id: str = "DOC-001",
    source_type: str = "player_document",
    point_id: UUID = POINT_ID_1,
    character_id: str = "C01",
    body: str = "테스트 사건 기록입니다.",
) -> RAGChunk:
    """테스트용 원본 RAGChunk 생성."""

    is_npc = source_type == "npc_knowledge"

    return RAGChunk(
        chunk_id=point_id,
        source_id=source_id,
        source_type=source_type,
        case_id="CASE-001",
        policy_id=(f"POL-K-{character_id}-01" if is_npc else "POL-CASE001-DOC-E01"),
        family="npc_knowledge" if is_npc else "evidence",
        access_scope=("character_only" if is_npc else "collected_evidence"),
        character_id=character_id if is_npc else None,
        incident_year=2016,
        content_hash="test-original-hash",
        search_text=f"검색용 텍스트 {source_id}",
        body=body,
    )


def fixed_config() -> ChunkingConfig:
    """고정 크기 청킹 설정."""

    return ChunkingConfig(
        mode=ChunkingMode.FIXED,
        min_chunk_chars=120,
        max_chunk_chars=800,
        overlap_chars=80,
    )


def semantic_config() -> ChunkingConfig:
    """의미 기반 청킹 설정."""

    return ChunkingConfig(
        mode=ChunkingMode.SEMANTIC_FIXED,
        min_chunk_chars=40,
        max_chunk_chars=180,
        overlap_chars=20,
        semantic_similarity_threshold=0.7,
    )


def test_whole_mode_preserves_source():
    """WHOLE 모드는 긴 원본도 분할하지 않는다."""

    source = make_source(body="A" * 1800)

    config = ChunkingConfig(mode=ChunkingMode.WHOLE)

    records = build_hybrid_chunks([source], config)

    assert len(records) == 1

    record = records[0]

    assert record.chunk == source
    assert record.parent_point_id == source.chunk_id
    assert record.chunk_index == 0
    assert record.chunk_count == 1


def test_short_semantic_document_preserved():
    """짧은 문서는 임베딩 없이 원본을 유지한다."""

    source = make_source()

    records = build_hybrid_chunks(
        [source],
        semantic_config(),
    )

    assert len(records) == 1
    assert records[0].chunk == source


def test_fixed_chunking_creates_subchunks():
    """긴 문서를 고정 크기로 분할한다."""

    source = make_source(body="A" * 1800)

    records = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    assert len(records) == 3

    assert [len(record.chunk.body) for record in records] == [
        800,
        800,
        360,
    ]

    assert [record.chunk_index for record in records] == [
        0,
        1,
        2,
    ]

    assert all(record.chunk_count == 3 for record in records)


def test_parent_uuid_preserved():
    """모든 하위 청크가 원본 UUID를 참조한다."""

    source = make_source(body="A" * 1800)

    records = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    assert all(record.parent_point_id == source.chunk_id for record in records)

    assert records[0].chunk.chunk_id == source.chunk_id


def test_subchunk_uuid_generation():
    """하위 청크 UUID가 결정적으로 생성된다."""

    source = make_source(body="A" * 1800)

    records = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    expected_ids = [
        source.chunk_id,
        uuid5(source.chunk_id, "rag-chunk:1"),
        uuid5(source.chunk_id, "rag-chunk:2"),
    ]

    actual_ids = [record.chunk.chunk_id for record in records]

    assert actual_ids == expected_ids
    assert len(set(actual_ids)) == 3


def test_chunk_ids_are_deterministic():
    """동일 데이터는 재실행해도 동일한 UUID를 생성한다."""

    source = make_source(body="A" * 1800)

    first = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    second = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    assert [record.chunk.chunk_id for record in first] == [
        record.chunk.chunk_id for record in second
    ]


def test_policy_metadata_preserved():
    """접근 정책 및 원본 메타데이터를 유지한다."""

    source = make_source(body="A" * 1800)

    records = build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    for record in records:
        chunk = record.chunk

        assert chunk.source_id == source.source_id
        assert chunk.source_type == source.source_type
        assert chunk.case_id == source.case_id
        assert chunk.policy_id == source.policy_id
        assert chunk.access_scope == source.access_scope
        assert chunk.content_hash == source.content_hash
        assert chunk.incident_year == source.incident_year


def test_npc_knowledge_separation():
    """서로 다른 NPC 지식이 혼합되지 않는다."""

    npc1 = make_source(
        source_id="K-C01-01",
        source_type="npc_knowledge",
        point_id=POINT_ID_1,
        character_id="C01",
        body="A" * 1000,
    )

    npc2 = make_source(
        source_id="K-C02-01",
        source_type="npc_knowledge",
        point_id=POINT_ID_2,
        character_id="C02",
        body="B" * 1000,
    )

    records = build_hybrid_chunks(
        [npc1, npc2],
        fixed_config(),
    )

    assert len(records) == 4

    for record in records:
        chunk = record.chunk

        assert chunk.access_scope == "character_only"

        if chunk.source_id == "K-C01-01":
            assert chunk.character_id == "C01"
            assert set(chunk.body) == {"A"}

        elif chunk.source_id == "K-C02-01":
            assert chunk.character_id == "C02"
            assert set(chunk.body) == {"B"}

        else:
            pytest.fail("알 수 없는 NPC 지식 카드")


def test_semantic_chunking_integration():
    """의미 기반 청킹이 실제 통합 파이프라인에서 작동한다."""

    text = " ".join(
        [
            "A" * 60 + ".",
            "B" * 60 + ".",
            "C" * 60 + ".",
            "D" * 60 + ".",
        ]
    )

    source = make_source(body=text)

    def embed_sentences(sentences):
        assert len(sentences) == 4

        return [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.0, 1.0],
        ]

    records = build_hybrid_chunks(
        [source],
        semantic_config(),
        embed_sentences=embed_sentences,
    )

    assert len(records) == 2

    assert records[0].chunk.body != records[1].chunk.body

    assert "".join(record.chunk.body for record in records) == text

    for record in records:
        assert record.chunk.policy_id == source.policy_id
        assert record.chunk.search_text == record.chunk.body


def test_original_source_not_modified():
    """분할 과정에서 원본 RAGChunk를 변경하지 않는다."""

    source = make_source(body="A" * 1800)

    original_data = source.model_dump()

    build_hybrid_chunks(
        [source],
        fixed_config(),
    )

    assert source.model_dump() == original_data


def test_duplicate_source_id_rejected():
    """동일 원본이 중복 입력되면 차단한다."""

    source = make_source()

    with pytest.raises(
        ValueError,
        match="중복 원본 ID",
    ):
        build_hybrid_chunks(
            [source, source],
            fixed_config(),
        )


def test_duplicate_uuid_rejected():
    """서로 다른 원본이 동일한 UUID를 사용하면 차단한다."""

    source1 = make_source(
        source_id="DOC-001",
        point_id=POINT_ID_1,
    )

    source2 = make_source(
        source_id="DOC-002",
        point_id=POINT_ID_1,
    )

    with pytest.raises(
        ValueError,
        match="중복 Chunk UUID",
    ):
        build_hybrid_chunks(
            [source1, source2],
            fixed_config(),
        )


def test_missing_embedding_function_rejected():
    """긴 문서의 Semantic 모드에 임베딩이 없으면 차단한다."""

    source = make_source(body="A" * 1000)

    with pytest.raises(
        ValueError,
        match="임베딩 함수가 필요합니다",
    ):
        build_hybrid_chunks(
            [source],
            semantic_config(),
        )


def test_empty_sources_rejected():
    """빈 데이터 입력을 차단한다."""

    with pytest.raises(
        ValueError,
        match="청킹 대상 데이터가 없습니다",
    ):
        build_hybrid_chunks(
            [],
            fixed_config(),
        )


def test_invalid_source_type_rejected():
    """RAGChunk가 아닌 입력을 차단한다."""

    with pytest.raises(
        TypeError,
        match="RAGChunk 타입만",
    ):
        build_hybrid_chunks(
            [{"source_id": "DOC-001"}],
            fixed_config(),
        )
